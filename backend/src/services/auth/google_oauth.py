"""
Google OAuth2 Authentication Service for Google Drive Integration.

Handles OAuth 2.0 flow:
1. Generate authorization URL (user visits to grant access)
2. Exchange authorization code for access/refresh tokens
3. Refresh access tokens when they expire
4. Store tokens in database per user
"""

import os
from datetime import datetime, timezone
from typing import Dict, Any, Optional, Tuple
from uuid import UUID
import json

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from google.auth.transport.requests import Request
from loguru import logger

from src.config import get_settings
from src.db.session import async_session_factory
from src.db.models import GoogleOAuthToken
from src.utils.encryption import encrypt_value, decrypt_value
from sqlalchemy import select


class GoogleOAuthService:
    """Service class for Google OAuth 2.0 authentication."""
    
    # OAuth scopes for Google Drive
    SCOPES = [
        'https://www.googleapis.com/auth/drive.readonly',
        'https://www.googleapis.com/auth/userinfo.email',
        'https://www.googleapis.com/auth/userinfo.profile',
        'openid'
    ]
    
    def __init__(self):
        """Initialize the Google OAuth service."""
        self.settings = get_settings()
    
    def _get_client_config(self) -> Optional[Dict[str, Any]]:
        """Get OAuth client configuration from settings."""
        client_id = self.settings.google.client_id
        client_secret = self.settings.google.client_secret
        
        if not client_id or not client_secret:
            return None
        
        return {
            'web': {
                'client_id': client_id,
                'client_secret': client_secret,
                'auth_uri': 'https://accounts.google.com/o/oauth2/auth',
                'token_uri': 'https://oauth2.googleapis.com/token',
                'redirect_uris': [self.settings.google.redirect_uri],
            }
        }
    
    def is_configured(self) -> bool:
        """Check if Google OAuth credentials are configured."""
        return self._get_client_config() is not None
    
    async def is_connected(self, user_id: UUID) -> Tuple[bool, Optional[str]]:
        """Check if user has valid Google credentials stored."""
        try:
            creds = await self.get_credentials(user_id)
            if creds and creds.valid:
                email = await self._get_user_email(creds)
                logger.info(f"User {user_id} is connected to Drive as {email}")
                return True, email
            
            logger.info(f"User {user_id} is NOT connected to Drive (creds valid: {creds.valid if creds else 'No creds'})")
            return False, None
        except Exception as e:
            logger.error(f"Error checking connection status: {e}")
            return False, None
    
    def get_auth_url(self, state: str = "") -> Optional[str]:
        """Generate the Google OAuth authorization URL."""
        client_config = self._get_client_config()
        if not client_config:
            return None
        
        flow = Flow.from_client_config(
            client_config,
            scopes=self.SCOPES,
            redirect_uri=self.settings.google.redirect_uri
        )
        
        auth_url, _ = flow.authorization_url(
            access_type='offline',
            prompt='consent select_account',
            include_granted_scopes='true',
            state=state
        )
        
        return auth_url
    
    async def handle_callback(
        self, 
        user_id: UUID, 
        authorization_code: str
    ) -> Tuple[bool, str]:
        """Handle OAuth callback and exchange code for tokens."""
        client_config = self._get_client_config()
        if not client_config:
            return False, "Google OAuth not configured"
        
        try:
            flow = Flow.from_client_config(
                client_config,
                scopes=self.SCOPES,
                redirect_uri=self.settings.google.redirect_uri
            )
            
            # Run blocking fetch_token in thread
            import asyncio
            logger.info("Exchanging authorization code for tokens...")
            await asyncio.to_thread(flow.fetch_token, code=authorization_code)
            credentials = flow.credentials
            
            logger.info(f"Got credentials. Refresh token present: {bool(credentials.refresh_token)}")
            
            await self._save_credentials(user_id, credentials)
            
            email = await self._get_user_email(credentials)
            logger.info(f"Successfully processed callback for user {user_id} ({email})")
            
            return True, f"Successfully connected as {email}" if email else "Successfully connected"
            
        except Exception as e:
            logger.error(f"Google OAuth error: {e}", exc_info=True)
            return False, f"Failed to authenticate: {str(e)}"

    async def disconnect(self, user_id: UUID) -> Tuple[bool, str]:
        """Disconnect Google account by removing stored tokens."""
        try:
            async with async_session_factory() as session:
                result = await session.execute(
                    select(GoogleOAuthToken).where(GoogleOAuthToken.user_id == user_id)
                )
                token = result.scalar_one_or_none()
                if token:
                    await session.delete(token)
                    await session.commit()
            
            return True, "Google Drive disconnected"
            
        except Exception as e:
            logger.error(f"Error disconnecting Google: {e}")
            return False, f"Failed to disconnect: {str(e)}"

    async def get_credentials(self, user_id: UUID) -> Optional[Credentials]:
        """Get valid credentials for a user, refreshing if necessary."""
        try:
            creds = await self._load_credentials(user_id)
            if not creds:
                # logger.debug(f"No credentials found for user {user_id}")
                return None
            
            if creds.expired and creds.refresh_token:
                try:
                    logger.info(f"refreshing credentials for user {user_id}")
                    # Run blocking refresh in thread
                    import asyncio
                    await asyncio.to_thread(creds.refresh, Request())
                    await self._save_credentials(user_id, creds)
                except Exception as e:
                    logger.error(f"Failed to refresh Google credentials: {e}")
                    return None
            
            return creds if creds.valid else None
        except Exception as e:
            logger.error(f"Error getting credentials: {e}")
            return None

    async def _load_credentials(self, user_id: UUID) -> Optional[Credentials]:
        """Load credentials from database."""
        try:
            async with async_session_factory() as session:
                result = await session.execute(
                    select(GoogleOAuthToken).where(GoogleOAuthToken.user_id == user_id)
                )
                token_record = result.scalar_one_or_none()
                
                if not token_record:
                    return None
                
                return Credentials(
                    token=decrypt_value(token_record.access_token),
                    refresh_token=decrypt_value(token_record.refresh_token) if token_record.refresh_token else None,
                    token_uri=token_record.token_uri,
                    client_id=token_record.client_id,
                    client_secret=decrypt_value(token_record.client_secret),
                    scopes=token_record.scopes.split(',') if token_record.scopes else None
                )
                
        except Exception as e:
            logger.error(f"Error loading Google credentials: {e}")
            return None

    async def _save_credentials(self, user_id: UUID, credentials: Credentials) -> None:
        """Save credentials to database."""
        try:
            async with async_session_factory() as session:
                result = await session.execute(
                    select(GoogleOAuthToken).where(GoogleOAuthToken.user_id == user_id)
                )
                existing = result.scalar_one_or_none()
                
                # Ensure expiry is timezone-aware if needed, or matched to DB
                # For now just saving as provided by google-auth
                
                token_data = {
                    'user_id': user_id,
                    'access_token': encrypt_value(credentials.token),
                    'refresh_token': encrypt_value(credentials.refresh_token) if credentials.refresh_token else None,
                    'token_uri': credentials.token_uri,
                    'client_id': credentials.client_id,
                    'client_secret': encrypt_value(credentials.client_secret),
                    'scopes': ','.join(credentials.scopes) if credentials.scopes else None,
                    'token_expiry': credentials.expiry,
                }
                
                if existing:
                    logger.debug(f"Updating existing credentials for user {user_id}")
                    for key, value in token_data.items():
                        setattr(existing, key, value)
                else:
                    logger.debug(f"Creating new credentials record for user {user_id}")
                    token_record = GoogleOAuthToken(**token_data)
                    session.add(token_record)
                
                await session.commit()
                logger.info(f"Successfully saved credentials for user {user_id}. Refresh token: {'Yes' if credentials.refresh_token else 'No'}")
                
        except Exception as e:
            logger.error(f"Error saving Google credentials: {e}", exc_info=True)
            raise
    
    async def _get_user_email(self, credentials: Credentials) -> Optional[str]:
        """Get the email of the authenticated user."""
        try:
            from googleapiclient.discovery import build
            import asyncio
            
            def _fetch_email():
                # Use oauth2 service to get identity info (requires userinfo.email scope)
                service = build('oauth2', 'v2', credentials=credentials)
                user_info = service.userinfo().get().execute()
                return user_info.get('email')
            
            return await asyncio.to_thread(_fetch_email)
            
        except Exception as e:
            logger.error(f"Failed to get user email: {e}")
            return None


# Singleton instance
google_oauth_service = GoogleOAuthService()
