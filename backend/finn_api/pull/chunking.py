from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from finn_api.pull.pdf_processing import ExtractedDocument, ExtractedPage


@dataclass(frozen=True)
class TextChunk:
    chunk_index: int
    page_start: int
    page_end: int
    section: str | None
    text: str
    token_count: int
    content_hash: str


def _estimate_tokens(text: str) -> int:
    return max(1, round(len(text.split()) * 1.35))


def _split_long_paragraph(text: str, word_limit: int) -> list[str]:
    words = text.split()
    if len(words) <= word_limit:
        return [text]
    return [
        " ".join(words[index : index + word_limit])
        for index in range(0, len(words), word_limit)
    ]


def _page_chunks(page: ExtractedPage, max_tokens: int) -> list[tuple[str | None, str]]:
    word_limit = max(1, int(max_tokens / 1.35))
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", page.text) if part.strip()]
    chunks: list[tuple[str | None, str]] = []
    current: list[str] = []
    current_section: str | None = None

    def flush() -> None:
        if current:
            chunks.append((current_section, "\n\n".join(current).strip()))
            current.clear()

    for paragraph in paragraphs:
        segments: list[str] = []
        for line in paragraph.splitlines():
            if line.startswith("## "):
                if segments:
                    body = "\n".join(segments).strip()
                    segments.clear()
                    for part in _split_long_paragraph(body, word_limit):
                        candidate = "\n\n".join((*current, part))
                        if current and _estimate_tokens(candidate) > max_tokens:
                            flush()
                        current.append(part)
                flush()
                current_section = line[3:].strip()[:240] or None
            else:
                segments.append(line)
        if segments:
            body = "\n".join(segments).strip()
            for part in _split_long_paragraph(body, word_limit):
                candidate = "\n\n".join((*current, part))
                if current and _estimate_tokens(candidate) > max_tokens:
                    flush()
                current.append(part)
    flush()
    return chunks


def chunk_document(document: ExtractedDocument, *, max_tokens: int = 700) -> tuple[TextChunk, ...]:
    if max_tokens < 40:
        raise ValueError("max_tokens must be at least 40.")
    chunks: list[TextChunk] = []
    for page in document.pages:
        for section, text in _page_chunks(page, max_tokens):
            content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
            chunks.append(
                TextChunk(
                    chunk_index=len(chunks),
                    page_start=page.page_number,
                    page_end=page.page_number,
                    section=section,
                    text=text,
                    token_count=_estimate_tokens(text),
                    content_hash=content_hash,
                )
            )
    return tuple(chunks)
