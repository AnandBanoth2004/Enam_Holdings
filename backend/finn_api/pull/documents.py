from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

import httpx

logger = logging.getLogger(__name__)
_PDF_CONTENT_TYPES = {"application/pdf", "application/octet-stream", "binary/octet-stream"}


class DocumentDownloadError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class DownloadedDocument:
    content: bytes
    content_hash: str
    content_type: str


class PrimaryDocumentDownloader:
    def __init__(
        self,
        *,
        client: httpx.Client | None = None,
        max_file_bytes: int = 30 * 1024 * 1024,
    ) -> None:
        if max_file_bytes <= 0:
            raise ValueError("max_file_bytes must be positive.")
        self.client = client or httpx.Client(
            timeout=httpx.Timeout(30.0, connect=10.0),
            headers={"User-Agent": "FINN primary-document research prototype"},
            follow_redirects=False,
        )
        self._owns_client = client is None
        self.max_file_bytes = max_file_bytes

    def close(self) -> None:
        if self._owns_client:
            self.client.close()

    def download(self, source_url: str, *, trusted_hosts: tuple[str, ...]) -> DownloadedDocument:
        parsed = urlparse(source_url)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or not _is_trusted_host(parsed.hostname, trusted_hosts)
        ):
            raise DocumentDownloadError(
                "untrusted_document_url",
                "The document URL must use HTTPS and a company-authorized source host.",
            )

        current_url = source_url
        try:
            for redirect_count in range(6):
                with self.client.stream("GET", current_url) as response:
                    if response.is_redirect:
                        if redirect_count == 5:
                            raise DocumentDownloadError(
                                "too_many_document_redirects",
                                "The company document source redirected too many times.",
                            )
                        location = response.headers.get("location")
                        if not location:
                            raise DocumentDownloadError(
                                "invalid_document_redirect",
                                "The company document source returned a redirect without a target.",
                            )
                        redirect_url = urljoin(current_url, location)
                        redirect = urlparse(redirect_url)
                        if (
                            redirect.scheme != "https"
                            or not redirect.hostname
                            or redirect.username is not None
                            or redirect.password is not None
                            or not _is_trusted_host(redirect.hostname, trusted_hosts)
                        ):
                            raise DocumentDownloadError(
                                "untrusted_document_redirect",
                                "The document redirected outside the approved company source hosts.",
                            )
                        current_url = redirect_url
                        continue

                    response.raise_for_status()
                    final = urlparse(str(response.url))
                    if (
                        final.scheme != "https"
                        or not final.hostname
                        or not _is_trusted_host(final.hostname, trusted_hosts)
                    ):
                        raise DocumentDownloadError(
                            "untrusted_document_redirect",
                            "The document redirected outside the approved company source hosts.",
                        )

                    content_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
                    if content_type and content_type not in _PDF_CONTENT_TYPES:
                        raise DocumentDownloadError(
                            "unsupported_document_mime_type",
                            f"Expected a PDF document, received {content_type}.",
                        )
                    declared_length = response.headers.get("content-length")
                    if declared_length and declared_length.isdecimal():
                        if int(declared_length) > self.max_file_bytes:
                            raise DocumentDownloadError(
                                "document_too_large",
                                "The PDF exceeds the configured download size limit.",
                            )

                    parts: list[bytes] = []
                    total = 0
                    for part in response.iter_bytes():
                        total += len(part)
                        if total > self.max_file_bytes:
                            raise DocumentDownloadError(
                                "document_too_large",
                                "The PDF exceeds the configured download size limit.",
                            )
                        parts.append(part)
                    break
            else:
                raise DocumentDownloadError(
                    "too_many_document_redirects",
                    "The company document source redirected too many times.",
                )
        except httpx.HTTPStatusError as error:
            logger.warning(
                "Primary document download failed host=%s status=%s",
                parsed.hostname,
                error.response.status_code,
            )
            raise DocumentDownloadError(
                "document_source_http_error",
                f"The company source returned HTTP {error.response.status_code}.",
            ) from error
        except httpx.TransportError as error:
            logger.warning(
                "Primary document source unavailable host=%s error_type=%s",
                parsed.hostname,
                type(error).__name__,
            )
            raise DocumentDownloadError(
                "document_source_unavailable",
                "The company document source could not be reached.",
            ) from error

        content = b"".join(parts)
        if not content.startswith(b"%PDF-"):
            raise DocumentDownloadError(
                "invalid_pdf_signature",
                "The company source did not return a valid PDF file.",
            )
        return DownloadedDocument(
            content=content,
            content_hash=hashlib.sha256(content).hexdigest(),
            content_type=content_type or "application/pdf",
        )


def _is_trusted_host(host: str, trusted_hosts: tuple[str, ...]) -> bool:
    normalized_host = host.casefold().rstrip(".")
    return any(
        normalized_host == trusted.casefold().strip(".")
        or normalized_host.endswith(f".{trusted.casefold().strip('.')}")
        for trusted in trusted_hosts
        if trusted.strip(".")
    )


__all__ = [
    "DocumentDownloadError",
    "DownloadedDocument",
    "PrimaryDocumentDownloader",
]
