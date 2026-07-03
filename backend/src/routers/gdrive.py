from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio.session import AsyncSession

from src.db.session import get_session
from src.db.models import User, Document, ProcessingStatus
from src.db.repositories.document import DocumentRepository
from src.services.auth import get_current_user
from src.services.auth.google_oauth import google_oauth_service
from src.services.ingestion.gdrive.google_drive_service import google_drive_service
from src.services.ingestion.main_processor import get_main_processor
from src.services.indexer.indexer import get_indexer
from loguru import logger


router = APIRouter(prefix="/sources/google", tags=["Google Drive"])


class GoogleAuthStatus(BaseModel):
    """Google Drive connection status."""
    configured: bool
    connected: bool
    email: str | None = None


class GoogleAuthUrlResponse(BaseModel):
    """OAuth authorization URL response."""
    auth_url: str


class GoogleDisconnectResponse(BaseModel):
    """Disconnect response."""
    success: bool
    message: str


class GoogleFileListResponse(BaseModel):
    """List of Google Drive files."""
    success: bool
    files: list
    next_page_token: str | None = None
    folder_id: str | None = None


class GoogleFileMetadataResponse(BaseModel):
    """File metadata response."""
    success: bool
    file: dict | None = None
    error: str | None = None


class GoogleFileImportResponse(BaseModel):
    """File import response."""
    success: bool
    document_id: UUID | None = None
    message: str


@router.get("/auth/status", response_model=GoogleAuthStatus)
async def get_google_status(
    user_id: UUID = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> GoogleAuthStatus:
    """
    Check Google Drive configuration and connection status.
    """
    try:
        is_configured = google_oauth_service.is_configured()
        is_connected, email = await google_oauth_service.is_connected(user_id)
        
        return GoogleAuthStatus(
            configured=is_configured,
            connected=is_connected,
            email=email
        )
    except Exception as e:
        logger.error(f"Failed to check Google auth status: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to check Google connection status")


@router.get("/auth/url", response_model=GoogleAuthUrlResponse)
async def get_google_auth_url(
    state: str = Query("", description="Optional state parameter for CSRF protection"),
    user_id: UUID = Depends(get_current_user),
) -> GoogleAuthUrlResponse:
    """
    Get Google OAuth authorization URL.
    
    The frontend should redirect the user to this URL.
    After granting permission, Google will redirect to the callback endpoint.
    """
    try:
        if not google_oauth_service.is_configured():
            raise HTTPException(
                status_code=400,
                detail="Google OAuth not configured. Please set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET."
            )
        
        auth_url = google_oauth_service.get_auth_url(state)
        logger.info(f"Generated Auth URL with redirect_uri: {google_oauth_service.settings.google.redirect_uri}")
        if not auth_url:
            raise HTTPException(status_code=500, detail="Failed to generate auth URL")
        
        return GoogleAuthUrlResponse(auth_url=auth_url)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to generate Google auth URL: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to generate authorization URL")



class GoogleCodeExchangeRequest(BaseModel):
    """Request model for exchanging auth code."""
    code: str
    state: Optional[str] = None

@router.post("/auth/exchange")
async def exchange_google_code(
    payload: GoogleCodeExchangeRequest,
    user_id: UUID = Depends(get_current_user),
) -> dict:
    """
    Exchange authorization code for tokens (POST version).
    """
    logger.info(f"Received Google code exchange request for user {user_id}")
    try:
        success, message = await google_oauth_service.handle_callback(user_id, payload.code)
        
        if success:
            return {
                "success": True,
                "message": message,
            }
        else:
            return {
                "success": False,
                "message": message,
            }
    except Exception as e:
        logger.error(f"Error executing code exchange: {e}", exc_info=True)
        return {
            "success": False,
            "message": "Failed to exchange authorization code",
        }

@router.get("/auth/callback")
async def handle_google_callback(
    code: str = Query(..., description="Authorization code from Google"),
    state: str = Query("", description="State parameter from OAuth flow"),
    user_id: UUID = Depends(get_current_user),
) -> dict:
    """
    Handle OAuth callback from Google (Legacy GET).
    """
    logger.info(f"Received Google callback for user {user_id}")
    try:
        success, message = await google_oauth_service.handle_callback(user_id, code)
        
        if success:
            return {
                "success": True,
                "message": message,
                "redirect_url": "/settings?google=connected"
            }
        else:
            return {
                "success": False,
                "message": message,
                "redirect_url": "/settings?google=error"
            }
    except Exception as e:
        logger.error(f"Google OAuth callback failed: {e}", exc_info=True)
        return {
            "success": False,
            "message": "OAuth callback processing failed",
            "redirect_url": "/settings?google=error"
        }


@router.post("/disconnect", response_model=GoogleDisconnectResponse)
async def disconnect_google(
    user_id: UUID = Depends(get_current_user),
) -> GoogleDisconnectResponse:
    """
    Disconnect Google Drive by removing stored tokens.
    """
    try:
        success, message = await google_oauth_service.disconnect(user_id)
        return GoogleDisconnectResponse(success=success, message=message)
    except Exception as e:
        logger.error(f"Failed to disconnect Google account: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to disconnect Google account")


@router.get("/files", response_model=GoogleFileListResponse)
async def list_google_files(
    folder_id: str | None = Query(None, description="Folder ID to list (root if not specified)"),
    page_size: int = Query(50, ge=1, le=100),
    page_token: str | None = Query(None),
    user_id: UUID = Depends(get_current_user),
) -> GoogleFileListResponse:
    """
    List files from Google Drive.
    
    Returns files filtered to types we can process (PDFs, documents, images, etc.).
    """
    try:
        result = await google_drive_service.list_files(
            user_id=user_id,
            folder_id=folder_id,
            page_size=page_size,
            page_token=page_token,
        )
        
        return GoogleFileListResponse(
            success=result['success'],
            files=result.get('files', []),
            next_page_token=result.get('next_page_token'),
            folder_id=result.get('folder_id'),
        )
    except Exception as e:
        logger.error(f"Failed to list Google Drive files: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to list Google Drive files")


@router.get("/files/search", response_model=GoogleFileListResponse)
async def search_google_files(
    query: str = Query(..., description="Search query"),
    mime_types: list[str] | None = Query(None, description="Optional MIME type filters"),
    page_size: int = Query(50, ge=1, le=100),
    page_token: str | None = None,
    user_id: UUID = Depends(get_current_user),
) -> GoogleFileListResponse:
    """
    Search for files in Google Drive.
    """
    try:
        result = await google_drive_service.search_files(
            user_id=user_id,
            query=query,
            mime_types=mime_types,
            page_size=page_size,
            page_token=page_token,
        )
        
        return GoogleFileListResponse(
            success=result['success'],
            files=result.get('files', []),
            next_page_token=result.get('next_page_token'),
        )
    except Exception as e:
        logger.error(f"Failed to search Google Drive files: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to search Google Drive files")


@router.get("/files/{file_id}/metadata", response_model=GoogleFileMetadataResponse)
async def get_google_file_metadata(
    file_id: str,
    user_id: UUID = Depends(get_current_user),
) -> GoogleFileMetadataResponse:
    """
    Get metadata for a specific file.
    """
    try:
        result = await google_drive_service.get_file_metadata(user_id, file_id)
        return GoogleFileMetadataResponse(
            success=result['success'],
            file=result.get('file'),
            error=result.get('error'),
        )
    except Exception as e:
        logger.error(f"Failed to get Google file metadata: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to get file metadata")


from src.services.queue.tasks import process_google_drive_task

@router.post("/files/{file_id}/import", response_model=GoogleFileImportResponse)
async def import_google_file(
    file_id: str,
    notebook_id: UUID = Query(..., description="Notebook to import into"),
    file_name: str | None = Query(None, description="Optional custom file name"),
    user_id: UUID = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> GoogleFileImportResponse:
    """
    Import a file from Google Drive to a notebook (Async Queue).
    
    Creates a pending document record and queues a job for the worker.
    """
    try:
        # Get file metadata first
        metadata_result = await google_drive_service.get_file_metadata(user_id, file_id)
        if not metadata_result['success']:
            raise HTTPException(status_code=400, detail=metadata_result['error'])
        
        name = file_name or metadata_result['file'].get('name', 'unknown')
        
        doc_repo = DocumentRepository(session)
        
        # 1. Create initial Document record in DB (PENDING)
        initial_doc = Document(
            notebook_id=notebook_id,
            filename=name,
            file_path=f"gdrive://{file_id}", # Virtual path for GDrive files
            mime_type=metadata_result['file'].get('mimeType', 'application/octet-stream'),
            status=ProcessingStatus.PENDING
        )
        saved_doc = await doc_repo.create(initial_doc)
        
        # 2. Add job to Queue (Procrastinate)
        await process_google_drive_task.defer_async(
            file_id=file_id,
            document_id=str(saved_doc.id),
            user_id=str(user_id),
            notebook_id=str(notebook_id)
        )
        
        return GoogleFileImportResponse(
            success=True,
            document_id=saved_doc.id,
            message=f"Import queued for {name}",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to import Google Drive file: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to import file from Google Drive")
