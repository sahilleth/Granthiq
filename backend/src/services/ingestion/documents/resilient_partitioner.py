from pathlib import Path
from io import BytesIO
from typing import List, Any, Union
from loguru import logger
from unstructured.partition.auto import partition

from src.services.ingestion.documents.pdf_utils import (
    check_tesseract_available,
    extract_pdf_text_from_path,
    extract_pdf_text_from_bytes
)

class ResilientPartitioner:
    """
    Handles document partitioning with robust fallback logic for PDFs.
    Encapsulates the complex try/except logic for Tesseract errors.
    """
    
    def __init__(
        self,
        strategy: str = "auto",
        include_page_breaks: bool = True,
        infer_table_structure: bool = True,
        extract_images: bool = True,
    ):
        self.strategy = strategy
        self.include_page_breaks = include_page_breaks
        self.infer_table_structure = infer_table_structure
        self.extract_images = extract_images

    def partition_from_path(self, file_path: Path) -> List[Any]:
        """
        Partition file from path with automatic fallback for PDFs.
        """
        file_ext = file_path.suffix.lower()
        strategy = self._get_strategy(file_ext)
        
        try:
            return partition(
                filename=str(file_path),
                strategy=strategy,
                chunking_strategy=None,
                include_page_breaks=self.include_page_breaks,
                infer_table_structure=self.infer_table_structure,
                extract_images_in_pdf=self.extract_images,
                languages=["eng"],
            )
        except Exception as e:
            return self._handle_partition_error(e, file_ext, file_path=file_path)

    def partition_from_bytes(self, file_bytes: bytes, filename: str) -> List[Any]:
        """
        Partition file from bytes with automatic fallback for PDFs.
        """
        file_ext = Path(filename).suffix.lower() if filename else ""
        strategy = self._get_strategy(file_ext)
        file_obj = BytesIO(file_bytes)
        
        try:
            return partition(
                file=file_obj,
                filename=filename,
                strategy=strategy,
                chunking_strategy=None,
                include_page_breaks=self.include_page_breaks,
                infer_table_structure=self.infer_table_structure,
                extract_images_in_pdf=self.extract_images,
                languages=["eng"],
            )
        except Exception as e:
            return self._handle_partition_error(e, file_ext, file_bytes=file_bytes)

    def _get_strategy(self, file_ext: str) -> str:
        """
        Determine partition strategy.
        
        For PDFs:
        - 'fast': No ML models, fast text extraction (default)
        - 'hi_res': Uses table detection models (very slow on CPU, ~5min for 20 pages)
        - 'auto': Same as 'fast' unless PDF_STRATEGY env var is set
        
        Set PDF_STRATEGY=hi_res if you need table structure extraction.
        """
        import os
        
        if file_ext == ".pdf":
            # Check for environment override
            env_strategy = os.getenv("PDF_STRATEGY", "").lower()
            if env_strategy in ("hi_res", "fast", "ocr_only"):
                logger.debug(f"Using PDF_STRATEGY from environment: {env_strategy}")
                return env_strategy
            
            # Default to 'fast' for performance
            # 'hi_res' loads table detection models (ResNet18) which takes 5+ minutes on CPU
            if self.strategy == "auto":
                return "fast"
        
        return self.strategy

    def _handle_partition_error(
        self, 
        e: Exception, 
        file_ext: str, 
        file_path: Path = None, 
        file_bytes: bytes = None
    ) -> List[Any]:
        """
        Handle partition errors, specifically fallback logic for Tesseract failures.
        """
        exception_type = type(e).__name__.lower()
        msg = str(e).lower()
        is_tesseract_error = (
            "tesseract" in exception_type
            or "tesseract" in msg
            or "tesseractnotfounderror" in exception_type
        )
        
        if file_ext == ".pdf" and is_tesseract_error:
            self._log_tesseract_warning(e)
            
            # Fallback to pypdf
            if file_path:
                page_texts = extract_pdf_text_from_path(file_path)
            else:
                page_texts = extract_pdf_text_from_bytes(file_bytes)
                
            return self._wrap_pages(page_texts)
            
        # If not a Tesseract error we can handle, re-raise
        logger.debug(f"Error during partition: {type(e).__name__}: {e}")
        raise e

    def _log_tesseract_warning(self, e: Exception):
        """Log helpful warning about Tesseract status."""
        tesseract_in_path = check_tesseract_available()
        error_name = type(e).__name__
        
        if tesseract_in_path:
            logger.warning(
                f"Tesseract is installed but unstructured couldn't find it ({error_name}: {e}). "
                "Falling back to pypdf text extraction."
            )
        else:
            logger.warning(
                f"Tesseract not found in PATH ({error_name}), falling back to pypdf text extraction."
            )

    def _wrap_pages(self, page_texts: List[str]) -> List[Any]:
        """Wrap plain text pages into objects compatible with Unstructured interface."""
        class _Page:
            def __init__(self, text: str, page_number: int):
                self.text = text
                self.metadata = {"page_number": page_number}
                self.category = "NarrativeText"  # Default category for fallback

        return [
            _Page(text=t, page_number=i + 1) 
            for i, t in enumerate(page_texts)
        ]

