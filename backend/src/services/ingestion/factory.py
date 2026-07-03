"""
Source Factory - Create processors for different source types.

Supported source types:
- file: Local files (PDF, DOCX, TXT, etc.)
- url: Web URLs
- youtube: YouTube videos
- gdrive: Google Drive files
"""

from typing import Union
from pathlib import Path
from uuid import UUID

from src.services.indexer.indexer import get_indexer
from src.services.ingestion.pipeline import IngestionPipeline
from src.services.ingestion.main_processor import MainProcessor
from src.services.ingestion.gdrive.google_drive_service import google_drive_service


def get_main_processor(
    auto_index: bool = True,
    **kwargs
):
    """
    Get a MainProcessor instance.
    
    Args:
        auto_index: Whether to automatically index documents after processing
        **kwargs: Additional arguments for MainProcessor
        
    Returns:
        MainProcessor or IngestionPipeline
    """
    processor = MainProcessor(**kwargs)
    
    if auto_index:
        indexer = get_indexer()
        return IngestionPipeline(processor, indexer)
    
    return processor


# Source type registry for routing to appropriate processor
SOURCE_PROCESSORS = {
    'file': 'process_file',
    'url': 'process_url',
    'youtube': 'process_youtube',
    'gdrive': 'process_gdrive',
}


def get_processor_for_source(source_type: str):
    """
    Get the processor method name for a source type.
    
    Args:
        source_type: Type of source ('file', 'url', 'youtube', 'gdrive')
        
    Returns:
        Method name string
        
    Raises:
        ValueError: If source_type is not supported
    """
    if source_type not in SOURCE_PROCESSORS:
        raise ValueError(f"Unsupported source type: {source_type}. Supported types: {list(SOURCE_PROCESSORS.keys())}")
    return SOURCE_PROCESSORS[source_type]


class SourceFactory:
    """
    Factory for creating and routing source processing.
    
    Usage:
        # Process a file
        doc = await SourceFactory.process(
            source_type='file',
            file_path='/path/to/file.pdf',
            user_id=user_id,
        )
        
        # Process a Google Drive file
        doc = await SourceFactory.process(
            source_type='gdrive',
            file_id='abc123',
            user_id=user_id,
        )
    """
    
    @staticmethod
    async def process(
        source_type: str,
        user_id: UUID,
        auto_chunk: bool = True,
        **kwargs
    ):
        """
        Process a source based on its type.
        
        Args:
            source_type: Type of source
            user_id: User's UUID (required for authentication)
            auto_chunk: Whether to apply chunking
            **kwargs: Source-specific arguments
                - file: file_path (str/Path)
                - url: url (str)
                - youtube: youtube_url (str)
                - gdrive: file_id (str)
                
        Returns:
            UnifiedDocument
        """
        processor = get_main_processor()
        method_name = get_processor_for_source(source_type)
        method = getattr(processor, method_name)
        
        # Add common arguments
        kwargs['user_id'] = user_id
        kwargs['auto_chunk'] = auto_chunk
        
        return await method(**kwargs)
    
    @staticmethod
    def can_process(source_type: str) -> bool:
        """Check if a source type is supported."""
        return source_type in SOURCE_PROCESSORS
    
    @staticmethod
    async def is_gdrive_connected(user_id: UUID) -> bool:
        """Check if Google Drive is connected for a user."""
        return await google_drive_service.is_connected(user_id)
