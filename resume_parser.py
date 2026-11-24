"""Extract plain text from a resume file (PDF, DOCX, or TXT).

Supported extensions: .pdf, .docx, .txt, .md
"""

from __future__ import annotations

import io
import os
from pathlib import Path

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".txt", ".md"}


class UnsupportedResumeFormatError(ValueError):
    """Raised when the resume file type is not supported."""


def extract_text(path: str | os.PathLike) -> str:
    """Extract text from a resume file on disk.

    Args:
        path: Path to a .pdf, .docx, .txt, or .md file.

    Returns:
        The extracted text, stripped of leading/trailing whitespace.

    Raises:
        FileNotFoundError: If the file does not exist.
        UnsupportedResumeFormatError: If the extension is not supported.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Resume file not found: {path}")
    suffix = path.suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise UnsupportedResumeFormatError(
            f"Unsupported resume format '{suffix}'. "
            f"Supported: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
        )
    data = path.read_bytes()
    return extract_text_from_bytes(data, filename=path.name)


def extract_text_from_bytes(data: bytes, filename: str = "resume.txt") -> str:
    """Extract text from resume bytes (for file uploads in Streamlit).

    Args:
        data: Raw file bytes.
        filename: Original filename, used only to pick the parser.

    Returns:
        The extracted text, stripped of leading/trailing whitespace.
    """
    suffix = Path(filename).suffix.lower()
    if suffix == ".pdf":
        return extract_pdf(io.BytesIO(data))
    if suffix == ".docx":
        return extract_docx(io.BytesIO(data))
    if suffix in {".txt", ".md"}:
        return data.decode("utf-8", errors="replace").strip()
    raise UnsupportedResumeFormatError(
        f"Unsupported resume format '{suffix}'. "
        f"Supported: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
    )


def extract_pdf(file_obj) -> str:
    """Extract text from a PDF file object using pypdf."""
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover
        raise ImportError(
            "pypdf is required to read PDF resumes. "
            "Install it with: pip install pypdf"
        ) from exc
    reader = PdfReader(file_obj)
    pages = []
    for page in reader.pages:
        pages.append(page.extract_text() or "")
    return "\n".join(pages).strip()


def extract_docx(file_obj) -> str:
    """Extract text from a DOCX file object using python-docx."""
    try:
        from docx import Document
    except ImportError as exc:  # pragma: no cover
        raise ImportError(
            "python-docx is required to read DOCX resumes. "
            "Install it with: pip install python-docx"
        ) from exc
    doc = Document(file_obj)
    lines = [p.text for p in doc.paragraphs if p.text.strip()]
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                if cell.text.strip():
                    lines.append(cell.text)
    return "\n".join(lines).strip()
