import os
import tempfile
from pathlib import Path
from typing import Optional, Union
from uuid import UUID

from loguru import logger

from src.schemas.document import UnifiedDocument, DocumentType
from src.services.ingestion.gdrive.google_drive_service import google_drive_service
from src.utils.exceptions import DocumentProcessingError


from src.services.ingestion.documents.document_processor import UnstructuredDocumentProcessor

class GoogleDriveProcessor:
    """Processor for files imported from Google Drive."""
    
    def __init__(self):
        """Initialize the Google Drive processor."""
        self.doc_processor = UnstructuredDocumentProcessor()
    
    async def process_file(
        self,
        file_id: str,
        user_id: UUID,
        file_name: Optional[str] = None,
        source_id: Optional[UUID] = None,
    ) -> UnifiedDocument:
        """
        Process a file from Google Drive.
        
        Args:
            file_id: The Google Drive file ID
            user_id: The user's UUID
            file_name: Optional custom file name
            source_id: Optional source document ID
            
        Returns:
            UnifiedDocument with processed content
        """
        try:
            # Get file metadata
            metadata_result = await google_drive_service.get_file_metadata(user_id, file_id)
            if not metadata_result['success']:
                raise DocumentProcessingError(metadata_result['error'])
            
            file_metadata = metadata_result['file']
            mime_type = file_metadata.get('mimeType', '')
            name = file_name or file_metadata.get('name', 'unknown')
            
            # Download/export file content
            content, error = await google_drive_service.get_file_content(user_id, file_id)
            if error:
                raise DocumentProcessingError(error)
            
            # Get file extension
            extension = await google_drive_service.get_file_extension(user_id, file_id) or ''
            
            # Create a temporary file for processing
            with tempfile.NamedTemporaryFile(
                suffix=extension, 
                delete=False
            ) as temp_file:
                temp_file.write(content)
                temp_path = Path(temp_file.name)
            
            try:
                # Use UnstructuredDocumentProcessor to extract text/content
                # This handles PDFs, DOCX, etc. correctly instead of loading raw bytes
                doc = await self.doc_processor.process(
                    file_path=temp_path,
                    user_id=user_id,
                    storage_path=f"gdrive://{file_id}",
                    source_id=source_id
                )
                
                # Update metadata with explicit GDrive info
                doc.filename = name
                doc.metadata['mime_type'] = mime_type
                doc.metadata['gdrive_file_id'] = file_id
                doc.source_type = self._mime_type_to_document_type(mime_type)

                logger.info(
                    f"Processed Google Drive file: {name} "
                    f"(type: {doc.source_type.value}, id: {file_id})"
                )
                
                return doc
                
            finally:
                # Clean up temp file
                if temp_path.exists():
                    temp_path.unlink()
            
        except DocumentProcessingError:
            raise
        except Exception as e:
            logger.error(f"Error processing Google Drive file: {e}")
            raise DocumentProcessingError(f"Failed to process file: {str(e)}")
    
    def _mime_type_to_document_type(self, mime_type: str) -> DocumentType:
        """
        Convert MIME type to DocumentType.
        
        Args:
            mime_type: The file's MIME type
            
        Returns:
            DocumentType enum value
        """
        mime_to_type = {
            # Documents
            'application/pdf': DocumentType.PDF,
            'text/plain': DocumentType.TXT,
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document': DocumentType.DOCX,
            'application/msword': DocumentType.DOCX,
            'application/vnd.google-apps.document': DocumentType.DOCX,
            # Spreadsheets
            'text/csv': DocumentType.CSV,
            'application/vnd.google-apps.spreadsheet': DocumentType.CSV,
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': DocumentType.XLSX,
            # Presentations
            'application/vnd.openxmlformats-officedocument.presentationml.presentation': DocumentType.PPTX,
            'application/vnd.google-apps.presentation': DocumentType.PPTX,
            # Images
            'image/jpeg': DocumentType.IMAGE,
            'image/png': DocumentType.IMAGE,
            'image/gif': DocumentType.IMAGE,
            'image/webp': DocumentType.IMAGE,
            # Audio
            'audio/mpeg': DocumentType.AUDIO,
            'audio/mp4': DocumentType.AUDIO,
            'audio/wav': DocumentType.AUDIO,
        }
        
        return mime_to_type.get(mime_type, DocumentType.UNKNOWN)
    
    async def process_google_doc(
        self,
        file_id: str,
        user_id: UUID,
        source_id: Optional[UUID] = None,
    ) -> UnifiedDocument:
        """
        Process a Google Doc specifically.
        
        Args:
            file_id: The Google Doc file ID
            user_id: The user's UUID
            source_id: Optional source document ID
            
        Returns:
            UnifiedDocument with text content
        """
        return await self.process_file(
            file_id=file_id,
            user_id=user_id,
            source_id=source_id,
        )
    
    async def process_google_sheet(
        self,
        file_id: str,
        user_id: UUID,
        source_id: Optional[UUID] = None,
    ) -> UnifiedDocument:
        """
        Process a Google Sheet specifically.
        
        Args:
            file_id: The Google Sheet file ID
            user_id: The user's UUID
            source_id: Optional source document ID
            
        Returns:
            UnifiedDocument with CSV content
        """
        return await self.process_file(
            file_id=file_id,
            user_id=user_id,
            source_id=source_id,
        )
    
    async def process_google_slides(
        self,
        file_id: str,
        user_id: UUID,
        source_id: Optional[UUID] = None,
    ) -> UnifiedDocument:
        """
        Process Google Slides specifically.
        
        Args:
            file_id: The Google Slides file ID
            user_id: The user's UUID
            source_id: Optional source document ID
            
        Returns:
            UnifiedDocument with text content
        """
        return await self.process_file(
            file_id=file_id,
            user_id=user_id,
            source_id=source_id,
        )
    
    async def process_drive_file(
        self,
        file_id: str,
        user_id: UUID,
        source_id: Optional[UUID] = None,
    ) -> UnifiedDocument:
        """
        Process any file from Google Drive.
        
        Automatically detects file type and processes accordingly.
        
        Args:
            file_id: The Drive file ID
            user_id: The user's UUID
            source_id: Optional source document ID
            
        Returns:
            UnifiedDocument with processed content
        """
        return await self.process_file(
            file_id=file_id,
            user_id=user_id,
            source_id=source_id,
        )


# Singleton instance
google_drive_processor = GoogleDriveProcessor()
