import hashlib
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Any, Optional, Union

from loguru import logger

from src.utils.exceptions import DocumentProcessingError
from src.utils.file_utils import validate_file_size, get_file_hash
from src.schemas.document import UnifiedDocument, DocumentType, ProcessingStatus
from src.services.ingestion.chunk_manager import apply_chunking_to_document_non_destructive
from src.config import get_settings
from src.services.ingestion.chunking.chunk_quality import is_junk_chunk
from src.services.ingestion.documents.structure_parser import StructureParser
from src.services.ingestion.documents.resilient_partitioner import ResilientPartitioner
from src.services.embeddings.embedding_config import get_llamaindex_embed_model
from llama_index.embeddings.huggingface import HuggingFaceEmbedding

def _ensure_uuid(val: Any) -> uuid.UUID:
    if isinstance(val, uuid.UUID):
        return val
    try:
        return uuid.UUID(str(val))
    except (ValueError, TypeError) as e:
        logger.debug(f"Could not parse UUID from value '{val}': {e}. Generating new UUID.")
        return uuid.uuid4()


def _detect_document_type(file_ext: str) -> DocumentType:
    ext_map = {
        '.pdf': DocumentType.PDF,
        '.txt': DocumentType.TXT,
        '.doc': DocumentType.DOCX,
        '.docx': DocumentType.DOCX,
    }
    return ext_map.get(file_ext, DocumentType.UNKNOWN)


class UnstructuredDocumentProcessor:
    """
    Document processor using unstructured's partition function.
    partition() automatically detects file types, so no need for extension validation.
    
    Refactored to use composed services:
    - ResilientPartitioner: Handles file parsing and fallback logic
    - StructureParser: Handles logical section grouping
    """

    def __init__(
        self,
        max_file_size_mb: int = 50,
        strategy: str = "auto",
        include_page_breaks: bool = True,
        chunking_strategy: Optional[str] = None,
        max_characters: int = 1000,
        combine_text_under_n_chars: int = 500,
        infer_table_structure: bool = True,
        extract_images: bool = True,
    ):
        self.max_file_size_mb = max_file_size_mb
        self.strategy = strategy
        self.chunking_strategy = chunking_strategy
        self.max_characters = max_characters
        self.combine_text_under_n_chars = combine_text_under_n_chars
        
        # Initialize partitioner
        self.partitioner = ResilientPartitioner(
            strategy=strategy,
            include_page_breaks=include_page_breaks,
            infer_table_structure=infer_table_structure,
            extract_images=extract_images
        )

    async def process(
        self, 
        file_path: Union[str, Path], 
        user_id: Optional[Union[str, uuid.UUID]] = None, 
        storage_path: Optional[str] = None, 
        source_id: Optional[Union[str, uuid.UUID]] = None,
        original_filename: Optional[str] = None,
    ) -> UnifiedDocument:
        try:
            file_path = Path(file_path)
            if not file_path.exists():
                raise DocumentProcessingError(f"File not found: {file_path}")

            file_ext = file_path.suffix.lower()
            validate_file_size(file_path, self.max_file_size_mb)

            # Use original filename when available (temp files have random names)
            display_name = original_filename or file_path.name

            logger.info(f"Processing document: {display_name} (type: {file_ext})")

            # 1. Partition Document
            elements = self.partitioner.partition_from_path(file_path)

            # 2. Create Base Document
            doc_type = _detect_document_type(file_ext)
            doc_id = _ensure_uuid(source_id) if source_id else uuid.uuid4()
            user_obj_id = _ensure_uuid(user_id) if user_id else get_settings().anonymous_user_id
            storage_path = storage_path or str(file_path)
            
            doc = UnifiedDocument(
                id=doc_id,
                user_id=user_obj_id,
                filename=display_name,
                source_type=doc_type,
                status=ProcessingStatus.COMPLETED,
                storage_path=storage_path,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
                metadata={
                    "file_name": display_name,
                    "file_hash": get_file_hash(file_path),
                    "file_type": file_ext,
                    "processing_strategy": self.strategy,
                },
            )

            # 3. Filter & Parse Structure
            good_elements = self._filter_elements(elements)
            logger.info(
                f"Filtered {len(elements) - len(good_elements)} low-quality elements "
                f"({len(good_elements)}/{len(elements)} kept)"
            )
            
            text_sections = StructureParser.parse_elements(good_elements)
            full_text, first_page = StructureParser.combine_sections(text_sections)
            
            # 4. Add Initial Chunk
            doc.add_chunk(
                content=full_text,
                chunk_index=0,
                page_number=first_page,
                metadata={},
            )

            # 5. Apply LlamaIndex Chunking
            self._apply_chunking(doc)

            logger.debug(f"Processed {doc.chunk_count} chunks for {file_path.name}.")
            return doc
            
        except Exception as e:
            logger.error(f"Error processing document {file_path}: {str(e)}")
            raise DocumentProcessingError(f"Failed to process document: {str(e)}") from e

    async def process_bytes(
        self, 
        file_bytes: bytes, 
        filename: str, 
        user_id: Optional[Union[str, uuid.UUID]] = None, 
        storage_path: Optional[str] = None, 
        source_id: Optional[Union[str, uuid.UUID]] = None,
    ) -> UnifiedDocument:
        try:
            logger.info(f"Processing document from bytes: {filename}")
            file_path = Path(filename)
            file_ext = file_path.suffix.lower()

            # 1. Partition Document
            elements = self.partitioner.partition_from_bytes(file_bytes, filename=filename)

            # 2. Create Base Document
            doc_type = _detect_document_type(file_ext)
            doc_id = _ensure_uuid(source_id) if source_id else uuid.uuid4()
            user_obj_id = _ensure_uuid(user_id) if user_id else get_settings().anonymous_user_id
            storage_path = storage_path or filename
            
            doc = UnifiedDocument(
                id=doc_id,
                user_id=user_obj_id,
                filename=filename,
                source_type=doc_type,
                status=ProcessingStatus.COMPLETED,
                storage_path=storage_path,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
                metadata={
                    "file_name": filename,
                    "file_type": file_ext,
                    "file_hash": hashlib.sha256(file_bytes).hexdigest(),
                    "processing_strategy": self.strategy,
                },
            )

            # 3. Filter & Parse Structure
            good_elements = self._filter_elements(elements)
            logger.info(
                f"Filtered {len(elements) - len(good_elements)} low-quality elements "
                f"({len(good_elements)}/{len(elements)} kept)"
            )
            
            text_sections = StructureParser.parse_elements(good_elements)
            full_text, first_page = StructureParser.combine_sections(text_sections)
            
            # 4. Add Initial Chunk
            doc.add_chunk(
                content=full_text,
                chunk_index=0,
                page_number=first_page,
                metadata={},
            )

            # 5. Apply LlamaIndex Chunking
            self._apply_chunking(doc)

            logger.debug(f"Processed {doc.chunk_count} chunks for {filename} (by bytes).")
            return doc
            
        except Exception as e:
            logger.error(f"Error processing document bytes for {filename}: {str(e)}")
            raise DocumentProcessingError(f"Failed to process document: {str(e)}") from e

    def _filter_elements(self, elements: List[Any]) -> List[Any]:
        """Filter out unwanted or junk elements."""
        good_elements = []
        for el in elements:
            category = getattr(el, "category", None) if hasattr(el, "category") else None
            
            # Filter out unwanted element types
            if category:
                if category in ["Header", "Footer", "PageNumber", "FigureCaption"]:
                    text = getattr(el, "text", "")
                    # Only skip short captions without content
                    if category == "FigureCaption" and len(text) > 100:
                        pass
                    else:
                        continue
            
            chunk_content = getattr(el, "text", "")
            if not chunk_content or not chunk_content.strip():
                continue
            
            # Filter junk chunks early
            if is_junk_chunk(chunk_content):
                continue
            
            good_elements.append(el)
        return good_elements

    def _apply_chunking(self, doc: UnifiedDocument):
        """Apply the configured chunking strategy to the document."""
        if self.chunking_strategy:
            overlap = max(
                0,
                min(self.combine_text_under_n_chars, self.max_characters // 2),
            )
            
            settings = get_settings()
            chunking_strategy = settings.rag.chunking_strategy
            embed_model = None
            
            if chunking_strategy == "semantic" or chunking_strategy == "auto":
                try:
                    # First, try to get existing embed_model from global Settings
                    
                    embed_model = get_llamaindex_embed_model()
                    logger.debug(f"DocumentProcessor: Retrieved embed_model: {type(embed_model).__name__ if embed_model else 'None'}")
                    
                    # If None, create HuggingFace embedder directly (simpler, avoids OpenAI fallback)
                    if embed_model is None:
                        logger.info("DocumentProcessor: Creating HuggingFace embedder directly for semantic chunking...")
                        try:
                            
                            model_name = settings.embedding.model
                            
                            # Create HuggingFace embedder directly - no global Settings manipulation
                            embed_model = HuggingFaceEmbedding(
                                model_name=model_name,
                                device='cpu',
                            )
                            logger.info(f"DocumentProcessor: Successfully created HuggingFaceEmbedding: {model_name}")
                        except Exception as create_error:
                            logger.warning(
                                f"DocumentProcessor: Failed to create HuggingFace embedder: {type(create_error).__name__}: {str(create_error)[:200]}\n"
                                f"Falling back to sentence splitting.",
                                exc_info=True
                            )
                            chunking_strategy = "sentence"
                            embed_model = None
                    
                    # Verify embed_model is actually set (not None)
                    if embed_model is None:
                        logger.warning("DocumentProcessor: Embed model is None. Using sentence splitting.")
                        chunking_strategy = "sentence"
                    else:
                        logger.debug(f"DocumentProcessor: Using embed_model for semantic chunking: {type(embed_model).__name__}")
                    
                except Exception as e:
                    # If we can't load embed_model, fall back to sentence splitting
                    logger.warning(
                        f"DocumentProcessor: Could not load embed_model for semantic chunking.\n"
                        f"Error: {type(e).__name__}: {str(e)[:200]}\n"
                        f"Falling back to sentence splitting."
                    )
                    chunking_strategy = "sentence"
                    embed_model = None
            
            # If strategy is semantic but embed_model is None, force sentence splitting
            if chunking_strategy == "semantic" and embed_model is None:
                logger.warning("DocumentProcessor: Semantic chunking requested but embed_model is None. Using sentence splitting instead.")
                chunking_strategy = "sentence"
            
            # Apply chunking ONCE - this replaces the element-level chunks
            apply_chunking_to_document_non_destructive(
                doc,
                chunk_size=self.max_characters,
                chunk_overlap=overlap,
                respect_sentence_boundary=True,
                strategy=chunking_strategy,
                embed_model=embed_model,
            )
            logger.info(f"Applied LlamaIndex chunking (strategy: {chunking_strategy}): {doc.chunk_count} chunks")
        else:
            # If no chunking strategy, keep the single combined chunk
            text_len = len(doc.chunks[0].content) if doc.chunks else 0
            logger.info(f"Using Unstructured elements as single chunk: {text_len} chars")


# Convenience wrappers

async def process_pdf(
    file_path: Union[str, Path],
    strategy: str = "auto",
    max_file_size_mb: int = 50,
    infer_table_structure: bool = True,
    chunking_strategy: Optional[str] = None,
    user_id: Optional[str] = None,
    storage_path: Optional[str] = None,
    source_id: Optional[str] = None,
) -> UnifiedDocument:
    processor = UnstructuredDocumentProcessor(
        max_file_size_mb=max_file_size_mb,
        strategy=strategy,
        infer_table_structure=infer_table_structure,
        chunking_strategy=chunking_strategy,
    )
    return await processor.process(
        file_path,
        user_id=user_id,
        storage_path=storage_path,
        source_id=source_id,
    )


async def process_text(
    file_path: Union[str, Path],
    max_file_size_mb: int = 50,
    chunking_strategy: Optional[str] = None,
    user_id: Optional[str] = None,
    storage_path: Optional[str] = None,
    source_id: Optional[str] = None,
) -> UnifiedDocument:
    processor = UnstructuredDocumentProcessor(
        max_file_size_mb=max_file_size_mb,
        strategy="fast",
        chunking_strategy=chunking_strategy,
    )
    return await processor.process(
        file_path,
        user_id=user_id,
        storage_path=storage_path,
        source_id=source_id,
    )


async def process_doc(
    file_path: Union[str, Path],
    max_file_size_mb: int = 50,
    infer_table_structure: bool = True,
    chunking_strategy: Optional[str] = None,
    user_id: Optional[str] = None,
    storage_path: Optional[str] = None,
    source_id: Optional[str] = None,
) -> UnifiedDocument:
    processor = UnstructuredDocumentProcessor(
        max_file_size_mb=max_file_size_mb,
        strategy="auto",
        infer_table_structure=infer_table_structure,
        chunking_strategy=chunking_strategy,
    )
    return await processor.process(
        file_path,
        user_id=user_id,
        storage_path=storage_path,
        source_id=source_id,
    )


async def process_document_auto(
    file_path: Union[str, Path],
    **kwargs,
) -> UnifiedDocument:
    processor = UnstructuredDocumentProcessor(**kwargs)
    return await processor.process(file_path)
