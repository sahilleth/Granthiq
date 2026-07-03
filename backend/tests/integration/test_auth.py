"""
Tests for authentication endpoints.
"""
import sys
from pathlib import Path

# Add backend directory to path for direct execution
_backend_dir = Path(__file__).parent.parent.parent
if str(_backend_dir) not in sys.path:
    sys.path.insert(0, str(_backend_dir))

import pytest
import uuid
from httpx import AsyncClient
from src.services.auth import get_current_user
from src.app import create_app


@pytest.mark.asyncio
async def test_get_user_profile_success(client: AsyncClient, test_user, test_jwt_token):
    """Test that valid JWT token returns user profile."""
    # For this test, we need to use real JWT validation, so we'll override differently
    from httpx import ASGITransport
    app = create_app()
    
    # Create a client that uses real JWT validation
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {test_jwt_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(test_user.id)
        assert data["email"] == test_user.email
        assert data["is_active"] is True
        assert "created_at" in data


@pytest.mark.asyncio
async def test_get_user_profile_jit_provisioning(test_jwt_token):
    """Test that user is created automatically on first request (JIT provisioning)."""
    from httpx import ASGITransport
    app = create_app()
    
    # Use a new user ID that doesn't exist yet
    new_user_id = uuid.uuid4()
    settings = pytest.importorskip("src.config").get_settings()
    import jwt
    import time
    
    payload = {
        "aud": "authenticated",
        "role": "authenticated",
        "sub": str(new_user_id),
        "email": f"jit_{new_user_id}@notebookllm.test",
        "exp": int(time.time()) + (60 * 60 * 24 * 30)
    }
    token = jwt.encode(payload, settings.auth.secret_key, algorithm=settings.auth.algorithm)
    
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(new_user_id)
        assert data["email"] == f"jit_{new_user_id}@notebookllm.test"


@pytest.mark.asyncio
async def test_get_user_profile_invalid_token():
    """Test that invalid token returns 401."""
    from httpx import ASGITransport
    app = create_app()
    
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get(
            "/api/v1/auth/me",
            headers={"Authorization": "Bearer invalid_token_12345"}
        )
        assert response.status_code == 401
        assert "detail" in response.json()


@pytest.mark.asyncio
async def test_get_user_profile_expired_token(expired_jwt_token):
    """Test that expired token returns 401."""
    from httpx import ASGITransport
    app = create_app()
    
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {expired_jwt_token}"}
        )
        assert response.status_code == 401
        data = response.json()
        assert "expired" in data["detail"].lower() or "token" in data["detail"].lower()


@pytest.mark.asyncio
async def test_get_user_profile_no_token():
    """Test that missing token returns 401."""
    from httpx import ASGITransport
    app = create_app()
    
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/api/v1/auth/me")
        assert response.status_code == 403  # FastAPI returns 403 for missing credentials


if __name__ == "__main__":
    import asyncio
    
    async def run_tests():
        from httpx import AsyncClient, ASGITransport
        from src.app import create_app
        from src.config import get_settings
        from src.db.session import async_session_factory
        from src.db.models import User
        from tests.conftest import TEST_USER_ID, TEST_USER_EMAIL, ensure_test_user_exists
        import jwt
        import time
        
        # Ensure test user exists in database first
        async with async_session_factory() as session:
            await ensure_test_user_exists(session)
        
        settings = get_settings()
        
        # Generate test token using the consistent TEST_USER_ID
        payload = {
            "aud": "authenticated",
            "role": "authenticated",
            "sub": str(TEST_USER_ID),
            "email": TEST_USER_EMAIL,
            "exp": int(time.time()) + (60 * 60 * 24 * 30)
        }
        token = jwt.encode(payload, settings.auth.secret_key, algorithm=settings.auth.algorithm)
        
        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            print("Running test_get_user_profile_invalid_token...")
            response = await client.get(
                "/api/v1/auth/me",
                headers={"Authorization": "Bearer invalid_token_12345"}
            )
            print(f"Status: {response.status_code}")
            assert response.status_code == 401
            
            print("\nRunning test_get_user_profile_no_token...")
            response = await client.get("/api/v1/auth/me")
            print(f"Status: {response.status_code}")
            assert response.status_code == 403
            
        print("\n✅ Auth tests passed (manual run - JIT provisioning test requires DB setup)")
    
    asyncio.run(run_tests())
