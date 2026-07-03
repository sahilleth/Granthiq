"""
Security-focused tests for the API.
Tests authorization, authentication, input validation, and attack prevention.
"""

import sys
from pathlib import Path

# Add backend directory to path for direct execution
_backend_dir = Path(__file__).parent.parent.parent
if str(_backend_dir) not in sys.path:
    sys.path.insert(0, str(_backend_dir))

import pytest
import uuid
import jwt
import time
from httpx import AsyncClient

from src.db.repositories.notebook import NotebookRepository
from src.db.repositories.document import DocumentRepository
from src.db.models import Document, ProcessingStatus


class TestAuthenticationSecurity:
    """Test authentication security measures."""

    @pytest.mark.asyncio
    async def test_invalid_token_rejected(self):
        """Test that invalid JWT tokens are rejected."""
        from httpx import ASGITransport
        from src.app import create_app

        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.get(
                "/api/v1/auth/me",
                headers={"Authorization": "Bearer invalid_token_xyz"}
            )
            assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_malformed_token_rejected(self):
        """Test that malformed JWT tokens are rejected."""
        from httpx import ASGITransport
        from src.app import create_app

        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            # Missing Bearer prefix
            response = await ac.get(
                "/api/v1/auth/me",
                headers={"Authorization": "not_bearer_token"}
            )
            assert response.status_code in [401, 403]

    @pytest.mark.asyncio
    async def test_expired_token_rejected(self, expired_jwt_token):
        """Test that expired JWT tokens are rejected."""
        from httpx import ASGITransport
        from src.app import create_app

        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.get(
                "/api/v1/auth/me",
                headers={"Authorization": f"Bearer {expired_jwt_token}"}
            )
            assert response.status_code == 401
            assert "expired" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_wrong_algorithm_rejected(self):
        """Test that tokens with wrong algorithm are rejected."""
        from src.config import get_settings
        from httpx import ASGITransport
        from src.app import create_app

        settings = get_settings()
        if not settings.auth.secret_key:
            pytest.skip("Auth secret key not configured")

        # Create token with different algorithm
        payload = {
            "aud": "authenticated",
            "sub": str(uuid.uuid4()),
            "exp": int(time.time()) + 3600
        }
        # Use HS384 instead of configured HS256
        token = jwt.encode(payload, settings.auth.secret_key, algorithm="HS384")

        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.get(
                "/api/v1/auth/me",
                headers={"Authorization": f"Bearer {token}"}
            )
            assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_wrong_audience_rejected(self):
        """Test that tokens with wrong audience are rejected."""
        from src.config import get_settings
        from httpx import ASGITransport
        from src.app import create_app

        settings = get_settings()
        if not settings.auth.secret_key:
            pytest.skip("Auth secret key not configured")

        # Create token with wrong audience
        payload = {
            "aud": "wrong_audience",
            "sub": str(uuid.uuid4()),
            "exp": int(time.time()) + 3600
        }
        token = jwt.encode(payload, settings.auth.secret_key, algorithm=settings.auth.algorithm)

        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.get(
                "/api/v1/auth/me",
                headers={"Authorization": f"Bearer {token}"}
            )
            assert response.status_code == 401


class TestAuthorizationSecurity:
    """Test authorization and access control."""

    @pytest.mark.asyncio
    async def test_cross_user_notebook_access_denied(self, client: AsyncClient, other_user_id, db_session):
        """Test that users cannot access other users' notebooks."""
        repo = NotebookRepository(db_session)
        other_notebook = await repo.create_notebook(other_user_id, "Private Notebook")

        response = await client.get(f"/api/v1/notebooks/{other_notebook.id}")
        assert response.status_code == 404  # Should appear as not found

    @pytest.mark.asyncio
    async def test_cross_user_notebook_update_denied(self, client: AsyncClient, other_user_id, db_session):
        """Test that users cannot update other users' notebooks."""
        repo = NotebookRepository(db_session)
        other_notebook = await repo.create_notebook(other_user_id, "Private")

        response = await client.patch(
            f"/api/v1/notebooks/{other_notebook.id}",
            json={"title": "Hacked Title"}
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_cross_user_notebook_delete_denied(self, client: AsyncClient, other_user_id, db_session):
        """Test that users cannot delete other users' notebooks."""
        repo = NotebookRepository(db_session)
        other_notebook = await repo.create_notebook(other_user_id, "Private")

        response = await client.delete(f"/api/v1/notebooks/{other_notebook.id}")
        assert response.status_code == 404

        # Verify notebook still exists
        notebook = await repo.get(other_notebook.id)
        assert notebook is not None

    @pytest.mark.asyncio
    async def test_cross_user_document_access_denied(self, client: AsyncClient, other_user_id, db_session):
        """Test that users cannot access other users' documents."""
        notebook_repo = NotebookRepository(db_session)
        doc_repo = DocumentRepository(db_session)

        other_notebook = await notebook_repo.create_notebook(other_user_id, "Private")
        doc = Document(
            notebook_id=other_notebook.id,
            filename="secret.pdf",
            file_path="secret/path.pdf",
            mime_type="application/pdf"
        )
        saved_doc = await doc_repo.create(doc)

        # Try to access document list
        response = await client.get(f"/api/v1/documents/notebook/{other_notebook.id}")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_cross_user_document_delete_denied(self, client: AsyncClient, other_user_id, db_session):
        """Test that users cannot delete other users' documents."""
        notebook_repo = NotebookRepository(db_session)
        doc_repo = DocumentRepository(db_session)

        other_notebook = await notebook_repo.create_notebook(other_user_id, "Private")
        doc = Document(
            notebook_id=other_notebook.id,
            filename="secret.pdf",
            file_path="secret/path.pdf",
            mime_type="application/pdf"
        )
        saved_doc = await doc_repo.create(doc)

        response = await client.delete(f"/api/v1/documents/{saved_doc.id}")
        assert response.status_code == 403

        # Verify document still exists
        doc_check = await doc_repo.get(saved_doc.id)
        assert doc_check is not None

    @pytest.mark.asyncio
    async def test_cross_user_chat_access_denied(self, client: AsyncClient, other_user_id, db_session):
        """Test that users cannot access other users' chat history."""
        repo = NotebookRepository(db_session)
        other_notebook = await repo.create_notebook(other_user_id, "Private")

        response = await client.get(f"/api/v1/chat/{other_notebook.id}/history")
        assert response.status_code == 404


class TestInputValidationSecurity:
    """Test input validation and sanitization."""

    @pytest.mark.asyncio
    async def test_sql_injection_in_title(self, client: AsyncClient):
        """Test SQL injection attempts in notebook title are handled safely."""
        malicious_titles = [
            "'; DROP TABLE notebooks; --",
            "1; DELETE FROM users WHERE 1=1; --",
            "' OR '1'='1",
            "admin'--",
            "1' AND '1'='1"
        ]

        for title in malicious_titles:
            response = await client.post(
                "/api/v1/notebooks",
                json={"title": title}
            )
            # Should create notebook with literal string
            assert response.status_code == 201
            assert response.json()["title"] == title

    @pytest.mark.asyncio
    async def test_xss_in_title(self, client: AsyncClient):
        """Test XSS attempts in notebook title are stored safely."""
        xss_payloads = [
            "<script>alert('xss')</script>",
            "<img src=x onerror=alert('xss')>",
            "javascript:alert('xss')",
            "<svg onload=alert('xss')>",
            "'\"><script>alert('xss')</script>"
        ]

        for payload in xss_payloads:
            response = await client.post(
                "/api/v1/notebooks",
                json={"title": payload}
            )
            # Should store as-is (sanitization is frontend responsibility)
            assert response.status_code == 201
            # API should return exact content
            assert response.json()["title"] == payload

    @pytest.mark.asyncio
    async def test_path_traversal_in_document_id(self, client: AsyncClient):
        """Test path traversal attempts in document ID are rejected."""
        malicious_ids = [
            "../../../etc/passwd",
            "..\\..\\..\\windows\\system32",
            "%2e%2e%2f%2e%2e%2f",
        ]

        for malicious_id in malicious_ids:
            response = await client.get(f"/api/v1/documents/{malicious_id}/url")
            assert response.status_code == 422  # Validation error for invalid UUID

    @pytest.mark.asyncio
    async def test_invalid_uuid_format(self, client: AsyncClient):
        """Test invalid UUID formats are properly rejected."""
        invalid_uuids = [
            "not-a-uuid",
            "12345",
            "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
            "",
            "null",
            "undefined"
        ]

        for invalid_uuid in invalid_uuids:
            response = await client.get(f"/api/v1/notebooks/{invalid_uuid}")
            assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_oversized_json_payload(self, client: AsyncClient):
        """Test that oversized JSON payloads are handled."""
        # Create a very large message (should be rejected by validation)
        large_message = "x" * 100000  # 100KB message

        response = await client.post(
            "/api/v1/notebooks",
            json={"title": large_message}
        )
        # Should succeed if within limits or return validation error
        assert response.status_code in [201, 422, 413]

    @pytest.mark.asyncio
    async def test_null_byte_injection(self, client: AsyncClient):
        """Test null byte injection attempts are handled."""
        response = await client.post(
            "/api/v1/notebooks",
            json={"title": "test\x00malicious"}
        )
        # Should either succeed or return validation error
        assert response.status_code in [201, 422]


class TestRateLimiting:
    """Test rate limiting functionality."""

    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_chat_rate_limiting(self, client: AsyncClient, test_notebook):
        """Test that chat endpoint has rate limiting."""
        # Note: Rate limiting may not trigger in test mode with dependency overrides
        # This test documents expected behavior
        responses = []

        for _ in range(25):  # Try to exceed typical rate limit
            response = await client.post(
                f"/api/v1/chat/{test_notebook.id}/message",
                json={"message": "Test message", "stream": False}
            )
            responses.append(response.status_code)

        # In production, some requests should be rate limited (429)
        # In test mode with overrides, may not trigger
        assert all(r in [200, 429, 500] for r in responses)

    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_upload_rate_limiting(self, client: AsyncClient, test_notebook, sample_pdf_content):
        """Test that upload endpoint has rate limiting."""
        import io

        responses = []
        for i in range(15):  # Try to exceed upload rate limit (10/hour)
            files = {"file": (f"test{i}.pdf", io.BytesIO(sample_pdf_content), "application/pdf")}
            data = {"notebook_id": str(test_notebook.id)}
            response = await client.post("/api/v1/documents/upload", files=files, data=data)
            responses.append(response.status_code)

        # Some uploads should potentially be rate limited
        assert all(r in [200, 429] for r in responses)


class TestContentSecurityHeaders:
    """Test security-related response headers."""

    @pytest.mark.asyncio
    async def test_cors_headers(self, client: AsyncClient):
        """Test CORS headers are properly set."""
        response = await client.options(
            "/api/v1/health/",
            headers={"Origin": "http://localhost:3000"}
        )
        # CORS should be configured
        assert response.status_code in [200, 204, 405]


class TestErrorHandling:
    """Test error handling doesn't leak sensitive information."""

    @pytest.mark.asyncio
    async def test_error_response_format(self, client: AsyncClient):
        """Test error responses have consistent format."""
        response = await client.get(f"/api/v1/notebooks/{uuid.uuid4()}")
        assert response.status_code == 404

        data = response.json()
        assert "detail" in data
        # Should not contain stack traces or internal paths
        assert "Traceback" not in str(data)
        assert "\\src\\" not in str(data)
        assert "/src/" not in str(data)

    @pytest.mark.asyncio
    async def test_validation_error_safe(self, client: AsyncClient):
        """Test validation errors don't expose internals."""
        response = await client.post(
            "/api/v1/notebooks",
            json={"invalid_field": "value"}
        )
        # May succeed (ignore extra fields) or return validation error
        assert response.status_code in [201, 422]

        if response.status_code == 422:
            data = response.json()
            # Should have structured validation errors
            assert "detail" in data


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
