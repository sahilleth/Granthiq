import asyncio
import sys
import os
import logging
from uuid import UUID

# Add the backend directory to sys.path
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from src.services.auth import get_current_user
from src.config import get_settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("test_auth")

def test_token_validation(token_str: str):
    """
    Simulates the Dependency Injection of FastAPI to test get_current_user logic directly.
    """
    logger.info("🔐 Testing Token Validation...")
    
    # Mock the Credentials object that FastAPI passes to the dependency
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token_str)
    
    # Manually get settings since Depends() only works in FastAPI context
    settings = get_settings()

    try:
        # Call the actual auth logic, injecting settings manually
        user_id = get_current_user(credentials, settings)
        
        logger.info("✅ SUCCESS! Token is valid.")
        logger.info(f"   👤 Extracted User ID: {user_id}")
        logger.info(f"   🆔 Type: {type(user_id)}")
        
        return user_id
        
    except HTTPException as e:
        logger.error(f"❌ AUTH FAILED: {e.detail} (Status: {e.status_code})")
    except Exception as e:
        logger.error(f"❌ UNEXPECTED ERROR: {e}")

if __name__ == "__main__":
    # Get token from args or prompt
    if len(sys.argv) > 1:
        token = sys.argv[1]
    else:
        print("\n👇 Paste the JWT Token below and press Enter:")
        token = input().strip()

    if not token:
        print("❌ No token provided.")
        sys.exit(1)

    # Clean potential quotes
    token = token.strip('"').strip("'")
    
    test_token_validation(token)
