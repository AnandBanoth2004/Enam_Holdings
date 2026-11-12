from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from io import BytesIO
from statistics import median
from typing import Literal

import pdfplumber
from pdfminer.pdfdocument import PDFEncryptionError
from pdfminer.pdfparser import PDFSyntaxError

DocumentType = Literal[
    "annual_report",
    "quarterly_result",
    "earnings_call_transcript",
    "investor_presentation",
]
ALLOWED_DOCUMENT_TYPES: tuple[DocumentType, ...] = (
    "annual_report",
    "quarterly_result",
    "earnings_call_transcript",
    "investor_presentation",
)

_TYPE_PATTERNS: tuple[tuple[DocumentType, re.Pattern[str]], ...] = (
    ("annual_report", re.compile(r"\bannual\s+reports?\b", re.IGNORECASE)),
    (
        "quarterly_result",
        re.compile(
            r"\b(?:quarterly\s+(?:financial\s+)?results?|"
            r"unaudited\s+(?:standalone\s+|consolidated\s+)?financial\s+results?)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "earnings_call_transcript",
        re.compile(r"\b(?:earnings|investor|analyst|con.?call)\s+transcript\b", re.IGNORECASE),
    ),
    (
        "investor_presentation",
        re.compile(r"\b(?:investor|analyst|financial)\s+presentation\b|\banalyst\s+meeting\b", re.IGNORECASE),
    ),
)
_QUARTER_PATTERN = re.compile(r"\bQ([1-4])\s*(?:OF\s*)?FY\s*['’]?(\d{2,4})\b", re.IGNORECASE)
_FY_RANGE_PATTERN = re.compile(
    r"\bFY\s*['’]?(20\d{2})\s*[-–/]\s*(\d{2,4})\b", re.IGNORECASE
)
_YEAR_RANGE_PATTERN = re.compile(r"\b(20\d{2})\s*[-–/]\s*(\d{2,4})\b")
_FY_PATTERN = re.compile(r"\bFY\s*['’]?(20\d{2}|\d{2})\b", re.IGNORECASE)
_FINANCIAL_STATEMENT_PATTERN = re.compile(
    r"\b(?:balance\s+sheet|statement\s+of\s+profit\s+and\s+loss|"
    r"statement\s+of\s+cash\s+flows?)\b",
    re.IGNORECASE,
)


class DocumentProcessingError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class ExtractedPage:
    page_number: int
    text: str


@dataclass(frozen=True)
class ExtractedDocument:
    pages: tuple[ExtractedPage, ...]
    document_type: DocumentType
    period_label: str | None
    period_start: date | None
    period_end: date | None
    extraction_method: str

    @property
    def text(self) -> str:
        return "\n\n".join(page.text for page in self.pages)


def _format_table(table: list[list[str | None]]) -> str:
    rows = [
        " | ".join(" ".join((cell or "").split()) for cell in row)
        for row in table
    ]
    return "\n".join(row for row in rows if row.strip(" |"))


def _heading_markup(text: str, page: pdfplumber.page.Page) -> str:
    sizes = [float(char["size"]) for char in page.chars if char.get("size")]
    median_size = median(sizes) if sizes else 0
    size_by_line: dict[str, list[float]] = {}
    for char in page.chars:
        line = " ".join((char.get("text") or "").split())
        if line and char.get("size"):
            size_by_line.setdefault(line, []).append(float(char["size"]))

    lines: list[str] = []
    for line in text.splitlines():
        normalized = " ".join(line.split())
        line_sizes = size_by_line.get(normalized, [])
        is_heading = (
            0 < len(normalized) <= 120
            and (
                normalized.isupper()
                or bool(re.match(r"^(?:[1-9]\d*(?:\.\d+)*|[A-Z])[\.)]?\s+\S", normalized))
                or (
                    bool(line_sizes)
                    and median(line_sizes) >= median_size * 1.18
                    and len(normalized.split()) <= 14
                )
            )
        )
        lines.append(f"## {normalized}" if is_heading else line)
    return "\n".join(lines).strip()


def _classify_document(text: str) -> DocumentType | None:
    for document_type, pattern in _TYPE_PATTERNS:
        if pattern.search(text):
            return document_type
    return None


def _fiscal_end_year(value: str) -> int:
    year = int(value)
    return year + 2000 if year < 100 else year


def _period_details(
    text: str,
) -> tuple[str | None, date | None, date | None, tuple[int, int] | None]:
    quarter = _QUARTER_PATTERN.search(text)
    range_match = _FY_RANGE_PATTERN.search(text)
    if range_match is None:
        range_match = _YEAR_RANGE_PATTERN.search(text)
    fiscal_match = _FY_PATTERN.search(text)

    if range_match:
        start_year = int(range_match.group(1))
        end_part = range_match.group(2)
        end_year = (
            int(f"20{end_part}")
            if len(end_part) == 2
            else int(end_part)
        )
    elif fiscal_match:
        end_year = _fiscal_end_year(fiscal_match.group(1))
        start_year = end_year - 1
    elif quarter:
        end_year = _fiscal_end_year(quarter.group(2))
        start_year = end_year - 1
    else:
        return None, None, None, None

    if quarter:
        quarter_number = int(quarter.group(1))
        period_label = f"Q{quarter_number} FY{end_year}"
        if quarter_number == 1:
            period_start, period_end = date(start_year, 4, 1), date(start_year, 6, 30)
        elif quarter_number == 2:
            period_start, period_end = date(start_year, 7, 1), date(start_year, 9, 30)
        elif quarter_number == 3:
            period_start, period_end = date(start_year, 10, 1), date(start_year, 12, 31)
        else:
            period_start, period_end = date(end_year, 1, 1), date(end_year, 3, 31)
        return period_label, period_start, period_end, (start_year, end_year)

    return (
        f"FY{start_year}-{str(end_year)[-2:]}",
        date(start_year, 4, 1),
        date(end_year, 3, 31),
        (start_year, end_year),
    )


def _period_matches(expected: str, extracted: str | None, years: tuple[int, int] | None) -> bool:
    if extracted is None or years is None:
        return False
    expected_quarter = _QUARTER_PATTERN.search(expected)
    extracted_quarter = _QUARTER_PATTERN.search(extracted)
    if expected_quarter:
        return (
            extracted_quarter is not None
            and expected_quarter.group(1) == extracted_quarter.group(1)
            and _fiscal_end_year(expected_quarter.group(2)) == years[1]
        )
    expected_years = _period_details(expected)
    return expected_years[3] == years


def _validate_identity(text: str, names: tuple[str, ...], ticker: str) -> None:
    normalized_text = " ".join(re.findall(r"[a-z0-9]+", text.casefold()))
    candidates = [name.strip() for name in names if name.strip()]
    for name in candidates:
        normalized_name = " ".join(re.findall(r"[a-z0-9]+", name.casefold()))
        if len(normalized_name) >= 5 and normalized_name in normalized_text:
            return
        distinctive = [
            token
            for token in normalized_name.split()
            if len(token) >= 4
            and token not in {"limited", "ltd", "company", "corporation", "industries"}
        ]
        if len(distinctive) >= 2 and all(token in normalized_text.split() for token in distinctive[:2]):
            return
    normalized_ticker = ticker.upper().removesuffix(".NS")
    if re.search(rf"\b{re.escape(normalized_ticker.casefold())}\b", normalized_text):
        return
    raise DocumentProcessingError(
        "company_identity_mismatch",
        f"The document does not identify the expected issuer ({ticker}).",
    )


def _ocr_page(pdf_bytes: bytes, page_number: int) -> str:
    try:
        import fitz
        import pytesseract
        from PIL import Image
    except ImportError as error:
        raise DocumentProcessingError(
            "ocr_unavailable",
            "This scanned PDF requires PyMuPDF, Pillow, and pytesseract for OCR.",
        ) from error

    try:
        with fitz.open(stream=pdf_bytes, filetype="pdf") as document:
            page = document.load_page(page_number - 1)
            pixmap = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
            image = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
            return pytesseract.image_to_string(image).strip()
    except pytesseract.TesseractNotFoundError as error:
        raise DocumentProcessingError(
            "ocr_unavailable",
            "The Tesseract executable is required to OCR scanned PDF pages.",
        ) from error
    except RuntimeError as error:
        raise DocumentProcessingError("ocr_failed", "Tesseract could not read this PDF page.") from error


def extract_pdf(
    pdf_bytes: bytes,
    *,
    ticker: str,
    company_names: tuple[str, ...],
    document_type: str,
    title: str,
    expected_period: str | None = None,
    ocr_min_characters: int = 35,
) -> ExtractedDocument:
    validated_type = next(
        (candidate for candidate in ALLOWED_DOCUMENT_TYPES if candidate == document_type),
        None,
    )
    if validated_type is None:
        raise DocumentProcessingError(
            "unsupported_document_type",
            "Pull research only accepts annual reports, quarterly results, earnings-call transcripts, and investor presentations.",
        )
    if not pdf_bytes.startswith(b"%PDF-"):
        raise DocumentProcessingError("invalid_pdf_signature", "The downloaded file is not a PDF.")

    try:
        pdf = pdfplumber.open(BytesIO(pdf_bytes))
    except (ValueError, OSError, PDFSyntaxError, PDFEncryptionError) as error:
        raise DocumentProcessingError("invalid_pdf", "The PDF could not be opened.") from error

    with pdf:
        if not pdf.pages:
            raise DocumentProcessingError("empty_pdf", "The PDF contains no pages.")
        pages: list[ExtractedPage] = []
        used_ocr = False
        for page_number, page in enumerate(pdf.pages, start=1):
            page_text = page.extract_text(layout=False) or ""
            layout_text = (
                page.extract_text(layout=True) or ""
                if _FINANCIAL_STATEMENT_PATTERN.search(page_text)
                else ""
            )
            formatted_tables = []
            for index, table in enumerate(page.extract_tables(), start=1):
                formatted = _format_table(table)
                if formatted:
                    formatted_tables.append(f"TABLE {index}:\n{formatted}")
            table_text = "\n\n".join(formatted_tables)
            layout_block = (
                f"FINANCIAL_STATEMENT_LAYOUT:\n{layout_text}" if layout_text else ""
            )
            combined = "\n\n".join(
                part for part in (page_text, table_text, layout_block) if part
            ).strip()
            if len(re.sub(r"\s+", "", combined)) < ocr_min_characters:
                ocr_text = _ocr_page(pdf_bytes, page_number)
                if ocr_text:
                    combined = "\n\n".join(part for part in (combined, ocr_text) if part)
                    used_ocr = True
            if not combined:
                raise DocumentProcessingError(
                    "page_text_unavailable",
                    f"No text could be extracted from PDF page {page_number}.",
                )
            pages.append(ExtractedPage(page_number, _heading_markup(combined, page)))

    first_pages_text = "\n".join(page.text for page in pages[:3])
    _validate_identity(first_pages_text, company_names, ticker)
    detected_type = _classify_document(pages[0].text) or _classify_document(title)
    if detected_type is not None and detected_type != validated_type:
        raise DocumentProcessingError(
            "document_type_mismatch",
            f"The document content looks like {detected_type}, not {validated_type}.",
        )

    full_text = "\n".join(page.text for page in pages[:8])
    period_label, period_start, period_end, years = _period_details(
        f"{title}\n{full_text}"
    )
    if expected_period and not _period_matches(expected_period, period_label, years):
        raise DocumentProcessingError(
            "reporting_period_mismatch",
            f"The document does not substantiate the requested reporting period ({expected_period}).",
        )

    return ExtractedDocument(
        pages=tuple(pages),
        document_type=validated_type,
        period_label=period_label,
        period_start=period_start,
        period_end=period_end,
        extraction_method="pdf_text+ocr" if used_ocr else "pdf_text",
    )
