import asyncio
from typing import List, Union, Optional
from pathlib import Path
from uuid import UUID
from loguru import logger
from langfuse import observe

from src.schemas.document import UnifiedDocument, DocumentType
from src.services.indexer.indexer import DocumentIndexer
from src.services.ingestion.main_processor import MainProcessor


# Constants for parallel processing
MAX_CONCURRENT_DOCUMENTS = 5  # Process up to 5 documents in parallel

class IngestionPipeline:
    """
    Orchestrates the ingestion process: Processing -> Indexing.
    Wraps MainProcessor (processing) and DocumentIndexer (indexing).
    """
    
    def __init__(
        self, 
        processor: MainProcessor, 
        indexer: Optional[DocumentIndexer] = None
    ):
        self.processor = processor
        self.indexer = indexer

    async def run(
        self,
        file_path: Union[str, Path],
        user_id: Optional[UUID] = None,
        storage_path: Optional[str] = None,
        source_id: Optional[UUID] = None,
        document_type: Optional[DocumentType] = None,
        auto_chunk: bool = True,
        index: bool = True,
    ) -> UnifiedDocument:
        """
        Run the ingestion pipeline for a single file.
        """
      
        doc = await self.processor.process_file(
            file_path=file_path,
            user_id=user_id,
            storage_path=storage_path,
            source_id=source_id,
            document_type=document_type,
            auto_chunk=auto_chunk,
        )
        
       
        if index and self.indexer:
            self._index_document(doc)
            
        return doc

    async def run_url(
        self,
        url: str,
        user_id: Optional[UUID] = None,
        source_id: Optional[UUID] = None,
        auto_chunk: bool = True,
        index: bool = True,
    ) -> UnifiedDocument:
        """
        Run the ingestion pipeline for a URL.
        """
        doc = await self.processor.process_url(
            url=url,
            user_id=user_id,
            source_id=source_id,
            auto_chunk=auto_chunk,
        )
        
        if index and self.indexer:
            self._index_document(doc)
            
        return doc

    async def run_youtube(
        self,
        url: str,
        user_id: Optional[UUID] = None,
        source_id: Optional[UUID] = None,
        auto_chunk: bool = True,
        index: bool = True,
    ) -> UnifiedDocument:
        """
        Run the ingestion pipeline for a YouTube video.
        """
        doc = await self.processor.process_youtube(
            youtube_url=url,
            user_id=user_id,
            source_id=source_id,
            auto_chunk=auto_chunk,
        )
        
        if index and self.indexer:
            self._index_document(doc)
            
        return doc

    async def run_batch(
        self,
        file_paths: List[Union[str, Path]],
        user_id: Optional[UUID] = None,
        auto_chunk: bool = True,
        index: bool = True,
    ) -> List[UnifiedDocument]:
        """
        Run the ingestion pipeline for a batch of files with parallel processing.
        
        Processes documents concurrently up to MAX_CONCURRENT_DOCUMENTS limit
        for optimal throughput while controlling resource usage.
        """
        if not file_paths:
            return []
        
        logger.info(f"Processing batch of {len(file_paths)} files with max {MAX_CONCURRENT_DOCUMENTS} concurrent")
        
        # Create semaphore to limit concurrent processing
        semaphore = asyncio.Semaphore(MAX_CONCURRENT_DOCUMENTS)
        
        async def process_single(file_path: Union[str, Path]) -> Optional[UnifiedDocument]:
            """Process a single file with semaphore-controlled concurrency."""
            async with semaphore:
                try:
                    return await self.processor.process_file(
                        file_path=file_path,
                        user_id=user_id,
                        auto_chunk=auto_chunk,
                    )
                except Exception as e:
                    logger.error(f"Failed to process file {file_path}: {e}")
                    return None
        
        # Process all files concurrently with limited parallelism
        tasks = [process_single(fp) for fp in file_paths]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Filter out failures and exceptions
        docs: List[UnifiedDocument] = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"Exception processing {file_paths[i]}: {result}")
            elif result is not None:
                docs.append(result)
        
        logger.info(f"Successfully processed {len(docs)}/{len(file_paths)} files")
        
        # Index documents in parallel if needed
        if index and self.indexer and docs:
            await self._index_documents_parallel(docs)
            
        return docs
    
    async def _index_documents_parallel(self, docs: List[UnifiedDocument]) -> None:
        """Index multiple documents in parallel."""
        if not docs:
            return
        
        # Use thread pool for CPU-bound indexing operations
        await asyncio.gather(*[
            asyncio.to_thread(self._index_document, doc)
            for doc in docs
        ])
        logger.info(f"Indexed {len(docs)} documents in parallel")

    @observe(as_type="span", name="pipeline_indexing")
    def _index_document(self, doc: UnifiedDocument):
        """Helper to index a document with tracing."""
        try:
            self.indexer.index_document(doc)
        except Exception as e:
            logger.error(f"Indexing failed in pipeline for doc {doc.id}: {e}")
          
