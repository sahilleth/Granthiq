import os
import jwt
import traceback
from jwt import PyJWKClient
from uuid import UUID

from fastapi import Depends, HTTPException, status, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from loguru import logger


from src.config import get_settings, Settings


security = HTTPBearer()

# Security Constants - Explicitly define allowed algorithms
ALLOWED_ALGORITHMS = ["ES256", "RS256"]
REQUIRED_AUDIENCE = "authenticated"

# Global Cache for JWKS Client to prevent re-fetching on every request
_jwks_client = None

def get_jwks_client(supabase_url: str):
    """
    Returns a cached PyJWKClient.
    This handles fetching keys and caching them automatically.
    """
    global _jwks_client
    if _jwks_client is None:
        base_url = supabase_url.strip().rstrip('/')
        if not base_url.startswith("http"):
            base_url = f"https://{base_url}"

        jwks_url = f"{base_url}/auth/v1/.well-known/jwks.json"
        _jwks_client = PyJWKClient(jwks_url)
    return _jwks_client

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Security(security),
    settings: Settings = Depends(get_settings)
) -> UUID:
    """
    Validate JWT token and return user ID.
    
    Security measures:
    - Only allows ES256/RS256 (asymmetric) algorithms
    - Never trusts algorithm from token header
    - Verifies issuer to prevent token replay from other sources
    - Validates audience claim
    """
    token = credentials.credentials

    try:
        # 1. Peek at Header to validate algorithm (but don't trust it)
        unverified_header = jwt.get_unverified_header(token)
        token_alg = unverified_header.get("alg")
        
        # SECURITY: Reject if algorithm not in explicit allowlist
        if token_alg not in ALLOWED_ALGORITHMS:
            logger.warning(f"[AUTH] Rejected token with unsupported algorithm: {token_alg}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token algorithm",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        # 2. Get Supabase URL for JWKS and issuer verification
        supabase_url = (
            settings.auth.supabase_url or 
            os.getenv("SUPABASE_URL") or 
            os.getenv("STORAGE_URL")
        )

        if not supabase_url:
            logger.error("CRITICAL: SUPABASE_URL missing. Cannot verify token.")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Server configuration error",
            )

        # Normalize URL
        base_url = supabase_url.strip().rstrip('/')
        if not base_url.startswith("http"):
            base_url = f"https://{base_url}"
        
        # Construct expected issuer
        expected_issuer = f"{base_url}/auth/v1"

        # 3. Choose verification method based on algorithm
        payload = None
        
        # Asymmetric Verification (JWKS)
        jwks_client = get_jwks_client(supabase_url)
        signing_key = jwks_client.get_signing_key_from_jwt(token)

        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256", "ES256"],  # Only asymmetric
            audience=REQUIRED_AUDIENCE,
            issuer=expected_issuer,
            leeway=10,
            options={
                "verify_iss": True,
                "verify_aud": True,
                "verify_exp": True,
                "require": ["exp", "sub", "aud"]
            }
        )

        # 5. Extract User ID
        user_id_str = payload.get("sub")
        
        if not user_id_str:
            logger.warning("[AUTH] Token missing 'sub' claim")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token: missing user ID",
                headers={"WWW-Authenticate": "Bearer"},
            )
            
        user_id = UUID(user_id_str)
        
        # Check for email verification status (if claim exists)
        # Standard Supabase JWTs might verify this via 'email_verified' or 'app_metadata'
        email_verified = payload.get("email_verified", False)
        if not email_verified and payload.get("app_metadata", {}).get("provider") == "email":
             # Depending on strictness, we could raise 403 here.
             # For now, we trust Supabase to not issue tokens if unverified (if configured).
             logger.debug(f"[AUTH] User {user_id} email_verified claim is: {email_verified}")

        logger.debug(f"[AUTH] Successfully authenticated user: {user_id}")
        return user_id

    except (jwt.PyJWTError, ValueError) as e:
        logger.warning(f"[AUTH] JWT Validation Failed: {type(e).__name__}: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except HTTPException:
        raise  # Re-raise FastAPI HTTP exceptions
    except Exception as e:
        logger.error(f"[AUTH] Auth System Error: {type(e).__name__}: {e}")
        logger.error(f"[AUTH] Traceback: {traceback.format_exc()}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Authentication system error",
        )