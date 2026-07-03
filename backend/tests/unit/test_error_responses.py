"""
Tests for standardized error responses.
"""

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from src.schemas.error import (
    ErrorCode,
    ErrorResponse,
    ErrorDetail,
    HTTP_STATUS_TO_ERROR_CODE,
    get_error_code_for_status,
)
from src.utils.errors import AppHTTPException, create_error_response


class TestErrorCode:
    """Tests for ErrorCode enum."""

    def test_error_code_values(self):
        """Test that all error codes are properly defined."""
        assert ErrorCode.NOTEBOOK_NOT_FOUND.value == "NOTEBOOK_NOT_FOUND"
        assert ErrorCode.DOCUMENT_NOT_FOUND.value == "DOCUMENT_NOT_FOUND"
        assert ErrorCode.VALIDATION_ERROR.value == "VALIDATION_ERROR"
        assert ErrorCode.INTERNAL_ERROR.value == "INTERNAL_ERROR"

    def test_error_code_is_string(self):
        """Test that ErrorCode can be used as string."""
        code = ErrorCode.NOTEBOOK_NOT_FOUND
        assert isinstance(code, str)
        assert code == "NOTEBOOK_NOT_FOUND"


class TestErrorResponseSchema:
    """Tests for ErrorResponse schema."""

    def test_error_response_model(self):
        """Test ErrorResponse model creation."""
        error = ErrorDetail(
            code=ErrorCode.NOTEBOOK_NOT_FOUND,
            message="Notebook not found",
            field="notebook_id",
        )

        response = ErrorResponse(error=error)

        assert response.error.code == ErrorCode.NOTEBOOK_NOT_FOUND
        assert response.error.message == "Notebook not found"
        assert response.error.field == "notebook_id"

    def test_error_response_with_request_id(self):
        """Test ErrorResponse with request ID."""
        error = ErrorDetail(
            code=ErrorCode.VALIDATION_ERROR, message="Validation failed"
        )

        response = ErrorResponse(error=error, request_id="test-request-123")

        assert response.request_id == "test-request-123"

    def test_error_response_serialization(self):
        """Test ErrorResponse JSON serialization."""
        error = ErrorDetail(
            code=ErrorCode.INVALID_INPUT,
            message="Invalid input",
            details={"field": "message", "min_length": 1},
        )

        response = ErrorResponse(error=error)
        json_data = response.model_dump()

        assert json_data["error"]["code"] == "INVALID_INPUT"
        assert json_data["error"]["message"] == "Invalid input"
        assert json_data["error"]["details"]["field"] == "message"


class TestHTTPStatusMapping:
    """Tests for HTTP status to error code mapping."""

    def test_status_code_mapping(self):
        """Test that status codes map to correct error codes."""
        assert get_error_code_for_status(400) == ErrorCode.INVALID_INPUT
        assert get_error_code_for_status(401) == ErrorCode.AUTH_REQUIRED
        assert get_error_code_for_status(403) == ErrorCode.AUTH_INSUFFICIENT_PERMISSIONS
        assert get_error_code_for_status(404) == ErrorCode.NOTEBOOK_NOT_FOUND
        assert get_error_code_for_status(409) == ErrorCode.NOTEBOOK_ALREADY_EXISTS
        assert get_error_code_for_status(413) == ErrorCode.INPUT_TOO_LONG
        assert get_error_code_for_status(422) == ErrorCode.VALIDATION_ERROR
        assert get_error_code_for_status(429) == ErrorCode.RATE_LIMIT_EXCEEDED
        assert get_error_code_for_status(500) == ErrorCode.INTERNAL_ERROR

    def test_unknown_status_code(self):
        """Test that unknown status codes map to INTERNAL_ERROR."""
        assert get_error_code_for_status(999) == ErrorCode.INTERNAL_ERROR


class TestAppHTTPException:
    """Tests for AppHTTPException class."""

    def test_basic_exception(self):
        """Test basic exception creation."""
        exc = AppHTTPException(
            status_code=404,
            code=ErrorCode.NOTEBOOK_NOT_FOUND,
            message="Notebook not found",
        )

        assert exc.status_code == 404
        assert exc.code == ErrorCode.NOTEBOOK_NOT_FOUND
        assert exc.message == "Notebook not found"

    def test_exception_with_field(self):
        """Test exception with field info."""
        exc = AppHTTPException(
            status_code=422,
            code=ErrorCode.VALIDATION_ERROR,
            message="Invalid message",
            field="message",
        )

        assert exc.field == "message"

    def test_exception_with_details(self):
        """Test exception with details."""
        exc = AppHTTPException(
            status_code=422,
            code=ErrorCode.VALIDATION_ERROR,
            message="Input too long",
            details={"max_length": 10000, "actual_length": 15000},
        )

        assert exc.details == {"max_length": 10000, "actual_length": 15000}

    def test_exception_defaults(self):
        """Test exception with minimal parameters."""
        exc = HTTPException(status_code=404)

        assert exc.status_code == 404

    def test_exception_detail(self):
        """Test that detail property works."""
        exc = AppHTTPException(
            status_code=404,
            code=ErrorCode.NOTEBOOK_NOT_FOUND,
            message="Notebook not found",
        )

        assert exc.detail == "Notebook not found"


class TestErrorResponseCreation:
    """Tests for create_error_response function."""

    def test_create_error_response(self):
        """Test creating error response."""
        response = create_error_response(
            status_code=404,
            code=ErrorCode.NOTEBOOK_NOT_FOUND,
            message="Notebook not found",
            field="notebook_id",
        )

        assert response.status_code == 404
        # Check response body
        import json

        body = json.loads(response.body)
        assert body["error"]["code"] == "NOTEBOOK_NOT_FOUND"
        assert body["error"]["message"] == "Notebook not found"
        assert body["error"]["field"] == "notebook_id"
        assert "request_id" in body

    def test_create_error_response_with_details(self):
        """Test creating error response with details."""
        response = create_error_response(
            status_code=422,
            code=ErrorCode.VALIDATION_ERROR,
            message="Validation failed",
            details={"errors": ["field required"]},
        )

        import json

        body = json.loads(response.body)
        assert body["error"]["details"]["errors"] == ["field required"]


@pytest.mark.asyncio
class TestErrorHandlerIntegration:
    """Integration tests for error handling in FastAPI."""

    async def test_validation_error_format(self, client):
        """Test that validation errors return standardized format."""
        # Send invalid request (empty message)
        response = await client.post(
            "/api/v1/chat/send", json={"message": "", "notebook_id": "test"}
        )

        # Should return 422 or 400
        assert response.status_code in [400, 422]

        data = response.json()
        assert "error" in data
        assert "code" in data["error"]
        assert "message" in data["error"]

    async def test_not_found_error_format(self, client):
        """Test that not found errors return standardized format."""
        # Request non-existent notebook
        response = await client.get(
            "/api/v1/notebooks/00000000-0000-0000-0000-000000000000"
        )

        assert response.status_code == 404

        data = response.json()
        assert "error" in data
        assert data["error"]["code"] == "NOTEBOOK_NOT_FOUND"

    async def test_unauthorized_error_format(self, client):
        """Test that unauthorized errors return standardized format."""
        # Request without auth
        response = await client.get("/api/v1/notebooks")

        # Should return 401 or 403
        assert response.status_code in [401, 403]

        data = response.json()
        assert "error" in data
        assert "code" in data["error"]

    async def test_error_includes_request_id(self, client):
        """Test that errors include request ID for tracing."""
        response = await client.get(
            "/api/v1/notebooks/00000000-0000-0000-0000-000000000000"
        )

        data = response.json()
        assert "request_id" in data
        assert data["request_id"] is not None
