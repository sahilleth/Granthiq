import re
import shutil
from io import BytesIO
from pathlib import Path
from typing import List, Optional

from loguru import logger
from pypdf import PdfReader

def check_tesseract_available() -> bool:
    """Check if Tesseract is available in PATH."""
    return shutil.which('tesseract') is not None

def clean_pdf_text(text: str) -> str:
    """
    Heuristic to fix broken newlines in PDF text.
    
    pypdf often returns text with hard newlines in the middle of sentences.
    This function fixes that by replacing single newlines with spaces
    while preserving double newlines as paragraph breaks.
    """
    if not text:
        return ""
    
    # 1. Replace double newlines with a placeholder
    text = text.replace('\n\n', '{PARAGRAPH_BREAK}')
    
    # 2. Replace single newlines with space
    text = text.replace('\n', ' ')
    
    # 3. Restore paragraphs
    text = text.replace('{PARAGRAPH_BREAK}', '\n\n')
    
    # 4. Collapse multiple spaces
    text = re.sub(r' +', ' ', text)
    
    # 5. Clean up spacing around punctuation
    text = re.sub(r'\s+([.,;:!?])', r'\1', text)
    
    return text.strip()

def extract_pdf_text_from_path(file_path: Path) -> List[str]:
    """Fallback PDF text extraction using pypdf."""
    texts: List[str] = []
    try:
        reader = PdfReader(str(file_path))
        for page in reader.pages:
            raw_text = page.extract_text() or ""
            texts.append(clean_pdf_text(raw_text))
    except Exception as e:
        logger.error(f"pypdf fallback failed for {file_path}: {e}")
        raise
    return texts

def extract_pdf_text_from_bytes(file_bytes: bytes) -> List[str]:
    """Fallback PDF text extraction from bytes using pypdf."""
    texts: List[str] = []
    try:
        reader = PdfReader(BytesIO(file_bytes))
        for page in reader.pages:
            raw_text = page.extract_text() or ""
            texts.append(clean_pdf_text(raw_text))
    except Exception as e:
        logger.error(f"pypdf fallback failed for PDF bytes: {e}")
        raise
    return texts

