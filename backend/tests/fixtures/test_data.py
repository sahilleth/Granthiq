"""
Test data helpers and fixtures for API tests.
"""
import io
from typing import BinaryIO


def create_sample_pdf() -> bytes:
    """
    Load actual Clinical PDF from uploads folder for testing.
    Returns bytes of the Clinical.pdf document.
    """
    from pathlib import Path
    pdf_path = Path(__file__).parent.parent.parent / "data" / "uploads" / "Clinical.pdf"
    if pdf_path.exists():
        with open(pdf_path, "rb") as f:
            return f.read()
    else:
        # Fallback to minimal PDF if file not found
        return b"""%PDF-1.4
1 0 obj
<<
/Type /Catalog
/Pages 2 0 R
>>
endobj
2 0 obj
<<
/Type /Pages
/Kids [3 0 R]
/Count 1
>>
endobj
3 0 obj
<<
/Type /Page
/Parent 2 0 R
/MediaBox [0 0 612 792]
/Contents 4 0 R
/Resources <<
/Font <<
/F1 <<
/Type /Font
/Subtype /Type1
/BaseFont /Helvetica
>>
>>
>>
endobj
4 0 obj
<<
/Length 44
>>
stream
BT
/F1 12 Tf
100 700 Td
(Test Document Content) Tj
ET
endstream
endobj
xref
0 5
0000000000 65535 f 
0000000009 00000 n 
0000000058 00000 n 
0000000115 00000 n 
0000000306 00000 n 
trailer
<<
/Size 5
/Root 1 0 R
>>
startxref
398
%%EOF"""


def create_sample_text() -> bytes:
    """
    Load actual notes.txt from uploads folder for testing.
    Returns bytes of plain text.
    """
    from pathlib import Path
    txt_path = Path(__file__).parent.parent.parent / "data" / "uploads" / "notes.txt"
    if txt_path.exists():
        with open(txt_path, "rb") as f:
            return f.read()
    else:
        # Fallback to simple text if file not found
        return b"""This is a test document with some content for testing purposes.
It contains multiple lines of text that can be used to test document processing.
The content is simple but sufficient for basic integration tests."""


def create_sample_markdown() -> bytes:
    """
    Create sample markdown content for testing.
    Returns bytes of markdown text.
    """
    return b"""# Test Document

This is a **test** document in Markdown format.

## Section 1

Some content here.

## Section 2

More content with `code` examples.
"""


def create_file_like_object(content: bytes) -> BinaryIO:
    """
    Create a file-like object from bytes content.
    Useful for testing file uploads.
    """
    return io.BytesIO(content)


def get_sample_pdf_file() -> tuple[str, BinaryIO, str]:
    """
    Get the Clinical PDF file tuple (filename, file_obj, mime_type).
    Ready to use with httpx file uploads.
    Uses the actual Clinical.pdf from uploads folder.
    """
    return ("Clinical.pdf", io.BytesIO(create_sample_pdf()), "application/pdf")


def get_sample_text_file() -> tuple[str, BinaryIO, str]:
    """
    Get a sample text file tuple (filename, file_obj, mime_type).
    Ready to use with httpx file uploads.
    """
    return ("test.txt", io.BytesIO(create_sample_text()), "text/plain")


def get_sample_markdown_file() -> tuple[str, BinaryIO, str]:
    """
    Get a sample markdown file tuple (filename, file_obj, mime_type).
    Ready to use with httpx file uploads.
    """
    return ("test.md", io.BytesIO(create_sample_markdown()), "text/markdown")
