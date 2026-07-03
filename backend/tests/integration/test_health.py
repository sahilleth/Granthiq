"""
Tests for health check endpoint.
"""
import sys
from pathlib import Path

# Add backend directory to path for direct execution
_backend_dir = Path(__file__).parent.parent.parent
if str(_backend_dir) not in sys.path:
    sys.path.insert(0, str(_backend_dir))

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_check(client: AsyncClient):
    """Test that health endpoint returns 200."""
    response = await client.get("/api/v1/health/")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "System is healthy"
    assert data["status_code"] == 200


@pytest.mark.asyncio
async def test_health_check_no_auth(client: AsyncClient):
    """Test that health endpoint doesn't require authentication."""
    # This should work without auth headers
    response = await client.get("/api/v1/health/")
    assert response.status_code == 200


if __name__ == "__main__":
    import asyncio
    
    async def run_tests():
        from httpx import AsyncClient, ASGITransport
        from src.app import create_app
        
        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            print("Running test_health_check...")
            response = await client.get("/api/v1/health/")
            print(f"Status: {response.status_code}")
            print(f"Response: {response.json()}")
            assert response.status_code == 200
            
            print("\nRunning test_health_check_no_auth...")
            response = await client.get("/api/v1/health/")
            print(f"Status: {response.status_code}")
            assert response.status_code == 200
            
        print("\n✅ All health tests passed!")
    
    asyncio.run(run_tests())
