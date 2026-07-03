import io
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from uuid import UUID

from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from loguru import logger

from src.services.auth.google_oauth import google_oauth_service


class GoogleDriveService:
    """Service class for Google Drive file operations."""
    
    # Mapping of Google Workspace MIME types to export formats
    EXPORT_MIME_TYPES = {
        'application/vnd.google-apps.document': {
            'export_mime': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            'extension': '.docx',
            'name': 'Google Doc'
        },
        'application/vnd.google-apps.spreadsheet': {
            'export_mime': 'text/csv',
            'extension': '.csv',
            'name': 'Google Sheet'
        },
        'application/vnd.google-apps.presentation': {
            'export_mime': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
            'extension': '.pptx',
            'name': 'Google Slides'
        },
    }
    
    # Supported file types
    SUPPORTED_MIME_TYPES = [
        # Documents
        'application/pdf',
        'text/plain',
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        'application/vnd.openxmlformats-officedocument.presentationml.presentation',
        'text/csv',
        # Images
        'image/jpeg',
        'image/png',
        'image/gif',
        'image/webp',
        # Audio
        'audio/mpeg',
        'audio/mp4',
        'audio/wav',
        'audio/x-m4a',
        'audio/aac',
        'audio/flac',
        # Google Workspace
        'application/vnd.google-apps.document',
        'application/vnd.google-apps.spreadsheet',
        'application/vnd.google-apps.presentation',
        # Folders
        'application/vnd.google-apps.folder',
    ]
    
    def __init__(self):
        """Initialize the Google Drive service."""
        self._service = None
    
    async def _get_service(self, user_id: UUID):
        """Get or create the Google Drive API service."""
        creds = await google_oauth_service.get_credentials(user_id)
        if not creds:
            return None
        
        # Do not cache service in self._service as it is user-specific!
        return build('drive', 'v3', credentials=creds)
    
    async def is_connected(self, user_id: UUID) -> bool:
        """Check if Google Drive is connected and accessible."""
        service = await self._get_service(user_id)
        return service is not None
    
    def _build_mime_query(self) -> str:
        """Build the query string for supported MIME types."""
        # Include regular files and folders
        types = self.SUPPORTED_MIME_TYPES + ['application/vnd.google-apps.folder']
        mime_query = " or ".join([f"mimeType = '{mt}'" for mt in types])
        return f"({mime_query})"

    async def list_files(
        self,
        user_id: UUID,
        folder_id: Optional[str] = None,
        page_size: int = 50,
        page_token: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        List files from Google Drive.
        
        Args:
            user_id: The user's UUID
            folder_id: Optional folder ID to list (None = root)
            page_size: Number of files per page
            page_token: Token for pagination
            
        Returns:
            Dict with files list and pagination info
        """
        service = await self._get_service(user_id)
        if not service:
            return {
                'success': False,
                'error': 'Google Drive not connected'
            }
        
        try:
            query_parts = ["trashed = false"]
            
            # Handle parent folder
            if folder_id:
                query_parts.append(f"'{folder_id}' in parents")
            else:
                # Default to root only to avoid showing all files in flat list
                query_parts.append("'root' in parents")
                
            # Filter by supported MIME types including folders
            query_parts.append(self._build_mime_query())
            
            query = " and ".join(query_parts)
            
            results = service.files().list(
                q=query,
                pageSize=page_size,
                pageToken=page_token,
                fields="nextPageToken, files(id, name, mimeType, size, modifiedTime, parents, iconLink, thumbnailLink)",
                orderBy="folder,name",
                supportsAllDrives=True,
                includeItemsFromAllDrives=True
            ).execute()
            
            files = results.get('files', [])
            
            # Process files (filtering is now done by API)
            processed_files = []
            for file in files:
                mime_type = file.get('mimeType', '')
                
                is_google_file = mime_type.startswith('application/vnd.google-apps.')
                is_folder = mime_type == 'application/vnd.google-apps.folder'
                
                export_info = self.EXPORT_MIME_TYPES.get(mime_type, {})
                
                processed_files.append({
                    'id': file.get('id'),
                    'name': file.get('name'),
                    'mime_type': mime_type,
                    'size': int(file.get('size', 0)) if file.get('size') else None,
                    'modified_time': file.get('modifiedTime'),
                    'is_folder': is_folder,
                    'is_google_file': is_google_file and not is_folder,
                    'export_extension': export_info.get('extension'),
                    'google_type': export_info.get('name'),
                    'icon_link': file.get('iconLink'),
                    'thumbnail_link': file.get('thumbnailLink'),
                })
            
            return {
                'success': True,
                'files': processed_files,
                'next_page_token': results.get('nextPageToken'),
                'folder_id': folder_id
            }
            
        except Exception as e:
            logger.error(f"Error listing Google files: {e}")
            return {
                'success': False,
                'error': f'Failed to list files: {str(e)}'
            }

    async def get_file_metadata(self, user_id: UUID, file_id: str) -> Dict[str, Any]:
        """
        Get detailed information about a specific file.
        
        Args:
            user_id: The user's UUID
            file_id: The Google Drive file ID
            
        Returns:
            Dict with file information
        """
        service = await self._get_service(user_id)
        if not service:
            return {
                'success': False,
                'error': 'Google Drive not connected'
            }
        
        try:
            file = service.files().get(
                fileId=file_id,
                fields="id, name, mimeType, size, modifiedTime, parents, webViewLink",
                supportsAllDrives=True
            ).execute()
            
            return {
                'success': True,
                'file': file
            }
            
        except Exception as e:
            logger.error(f"Error getting file metadata: {e}")
            return {
                'success': False,
                'error': f'Failed to get file info: {str(e)}'
            }
    
    async def get_file_content(
        self,
        user_id: UUID,
        file_id: str
    ) -> Tuple[Optional[bytes], Optional[str]]:
        """
        Download file content from Google Drive.
        
        Args:
            user_id: The user's UUID
            file_id: The Google Drive file ID
            
        Returns:
            Tuple of (file_content, error_message)
        """
        service = await self._get_service(user_id)
        if not service:
            return None, 'Google Drive not connected'
        
        try:
            # Get file metadata to determine type
            file_info = service.files().get(
                fileId=file_id,
                fields="id, name, mimeType",
                supportsAllDrives=True
            ).execute()
            
            mime_type = file_info.get('mimeType', '')
            
            # Check if it's a Google Workspace file that needs export
            if mime_type in self.EXPORT_MIME_TYPES:
                return self._export_google_file(service, file_id, mime_type)
            else:
                return self._download_regular_file(service, file_id)
            
        except Exception as e:
            logger.error(f"Error downloading file: {e}")
            return None, f'Failed to download file: {str(e)}'
    
    def _download_regular_file(
        self,
        service,
        file_id: str
    ) -> Tuple[Optional[bytes], Optional[str]]:
        """Download a regular (non-Google) file."""
        try:
            request = service.files().get_media(fileId=file_id)
            
            buffer = io.BytesIO()
            downloader = MediaIoBaseDownload(buffer, request)
            
            done = False
            while not done:
                status, done = downloader.next_chunk()
            
            return buffer.getvalue(), None
            
        except Exception as e:
            logger.error(f"Download failed: {e}")
            return None, f'Download failed: {str(e)}'
    
    def _export_google_file(
        self,
        service,
        file_id: str,
        mime_type: str
    ) -> Tuple[Optional[bytes], Optional[str]]:
        """Export a Google Workspace file to a standard format."""
        export_info = self.EXPORT_MIME_TYPES.get(mime_type)
        if not export_info:
            return None, f'Unsupported Google file type: {mime_type}'
        
        try:
            request = service.files().export_media(
                fileId=file_id,
                mimeType=export_info['export_mime']
            )
            
            buffer = io.BytesIO()
            downloader = MediaIoBaseDownload(buffer, request)
            
            done = False
            while not done:
                status, done = downloader.next_chunk()
            
            return buffer.getvalue(), None
            
        except Exception as e:
            logger.error(f"Export failed: {e}")
            return None, f'Export failed: {str(e)}'
    
    async def get_shared_drives(self, user_id: UUID) -> Dict[str, Any]:
        """
        List shared drives the user has access to.
        
        Args:
            user_id: The user's UUID
            
        Returns:
            Dict with shared drives list
        """
        service = await self._get_service(user_id)
        if not service:
            return {
                'success': False,
                'error': 'Google Drive not connected'
            }
        
        try:
            results = service.drives().list(
                pageSize=50,
                fields="nextPageToken, drives(id, name)"
            ).execute()
            
            return {
                'success': True,
                'drives': results.get('drives', []),
                'next_page_token': results.get('nextPageToken')
            }
            
        except Exception as e:
            logger.error(f"Error listing shared drives: {e}")
            return {
                'success': False,
                'error': f'Failed to list shared drives: {str(e)}'
            }

    async def search_files(
        self,
        user_id: UUID,
        query: str,
        mime_types: Optional[List[str]] = None,
        page_size: int = 50,
        page_token: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Search for files in Google Drive.
        
        Args:
            user_id: The user's UUID
            query: Search query string
            mime_types: Optional list of MIME types to filter
            page_size: Number of results per page
            page_token: Token for pagination
            
        Returns:
            Dict with search results
        """
        service = await self._get_service(user_id)
        if not service:
            return {
                'success': False,
                'error': 'Google Drive not connected'
            }
        
        try:
            query_parts = [f"fullText contains '{query}'", "trashed = false"]
            
            if mime_types:
                mime_query = " or ".join([f"mimeType = '{mt}'" for mt in mime_types])
                query_parts.append(f"({mime_query})")
            else:
                 # Default to supported types if no filter provided
                query_parts.append(self._build_mime_query())
            
            query = " and ".join(query_parts)
            
            results = service.files().list(
                q=query,
                pageSize=page_size,
                pageToken=page_token,
                fields="nextPageToken, files(id, name, mimeType, size, modifiedTime)",
                orderBy="modifiedTime desc",
                supportsAllDrives=True,
                includeItemsFromAllDrives=True
            ).execute()
            
            return {
                'success': True,
                'files': results.get('files', []),
                'next_page_token': results.get('nextPageToken')
            }
            
        except Exception as e:
            logger.error(f"Error searching files: {e}")
            return {
                'success': False,
                'error': f'Failed to search files: {str(e)}'
            }
    
    async def get_file_extension(self, user_id: UUID, file_id: str) -> Optional[str]:
        """
        Get the appropriate file extension for a Drive file.
        
        Args:
            user_id: The user's UUID
            file_id: File ID
            
        Returns:
            File extension (e.g., '.pdf', '.docx') or None
        """
        service = await self._get_service(user_id)
        if not service:
            return None
        
        try:
            file = service.files().get(
                fileId=file_id,
                fields="name, mimeType"
            ).execute()
            
            mime_type = file.get('mimeType', '')
            
            # Check if Google Workspace file
            if mime_type in self.EXPORT_MIME_TYPES:
                return self.EXPORT_MIME_TYPES[mime_type]['extension']
            
            # Regular file - get extension from name
            name = file.get('name', '')
            if '.' in name:
                return '.' + name.rsplit('.', 1)[-1].lower()
            
            return None
            
        except Exception:
            return None


# Singleton instance
google_drive_service = GoogleDriveService()
