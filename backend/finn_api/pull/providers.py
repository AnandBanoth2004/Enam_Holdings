from __future__ import annotations

import math
from typing import Protocol

import httpx


class EmbeddingProvider(Protocol):
    embedding_model: str

    def embed(self, texts: list[str]) -> list[list[float]]: ...


class ResearchModel(Protocol):
    model: str

    def answer(self, *, question: str, evidence: list[dict[str, str]]) -> str: ...


class ModelProviderError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class OpenAICompatibleProvider:
    def __init__(
        self,
        *,
        api_base_url: str,
        api_key: str,
        embedding_model: str,
        research_model: str,
        embedding_dimensions: int = 1536,
        timeout_seconds: float = 30,
        client: httpx.Client | None = None,
    ) -> None:
        self.api_base_url = api_base_url.rstrip("/")
        self.api_key = api_key
        self.embedding_model = embedding_model
        self.research_model = research_model
        self.embedding_dimensions = embedding_dimensions
        self.model = research_model
        self.client = client or httpx.Client(
            timeout=httpx.Timeout(timeout_seconds, connect=10.0),
            headers={"Authorization": f"Bearer {api_key}"},
        )
        self._owns_client = client is None

    def close(self) -> None:
        if self._owns_client:
            self.client.close()

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        try:
            response = self.client.post(
                f"{self.api_base_url}/embeddings",
                json={"model": self.embedding_model, "input": texts},
            )
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as error:
            raise ModelProviderError(
                "embedding_provider_error",
                "The configured embedding provider could not complete the request.",
            ) from error

        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, list) or len(data) != len(texts):
            raise ModelProviderError(
                "embedding_provider_invalid_response",
                "The embedding provider returned an invalid response.",
            )
        try:
            ordered = sorted(data, key=lambda item: int(item["index"]))
            vectors = [[float(value) for value in item["embedding"]] for item in ordered]
        except (KeyError, TypeError, ValueError) as error:
            raise ModelProviderError(
                "embedding_provider_invalid_response",
                "The embedding provider returned malformed vectors.",
            ) from error
        if any(
            not vector
            or len(vector) != self.embedding_dimensions
            or any(not math.isfinite(value) for value in vector)
            for vector in vectors
        ):
            raise ModelProviderError(
                "embedding_provider_invalid_response",
                "The embedding provider returned vectors with an invalid size or value.",
            )
        return vectors

    def answer(self, *, question: str, evidence: list[dict[str, str]]) -> str:
        messages = [
            {
                "role": "system",
                "content": (
                    "Answer only from the supplied primary-source excerpts. Do not use prior "
                    "knowledge, outside sources, or infer missing facts. Return a JSON object "
                    "with keys claims and limitations. Each claim must contain text, claim_type "
                    "(reported_fact, calculation, or interpretation), evidence_quotes (a list "
                    "of objects with chunk_id and quote copied exactly from that chunk), and "
                    "confidence from 0 to 1. Every factual claim must have at least one exact "
                    "quote. Use no claim if the excerpts do not support an answer. Do not "
                    "invent values, periods, units, or citations."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Question: {question}\n\n"
                    f"Evidence JSON: {evidence}"
                ),
            },
        ]
        try:
            response = self.client.post(
                f"{self.api_base_url}/chat/completions",
                json={
                    "model": self.research_model,
                    "messages": messages,
                    "temperature": 0,
                    "response_format": {"type": "json_object"},
                },
            )
            response.raise_for_status()
            payload = response.json()
            content = payload["choices"][0]["message"]["content"]
            if not isinstance(content, str):
                raise TypeError("Model response content must be JSON text.")
            return content
        except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError) as error:
            raise ModelProviderError(
                "research_model_error",
                "The configured research model could not produce a valid response.",
            ) from error
