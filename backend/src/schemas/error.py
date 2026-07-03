"""
Standardized error response schemas and error codes.
"""

from enum import Enum
from typing import Optional, Any, Dict
from pydantic import BaseModel, Field


class ErrorCode(str, Enum):
    """Standardized error codes for the application."""

    # Authentication & Authorization
    AUTH_REQUIRED = "AUTH_REQUIRED"
    AUTH_INVALID_TOKEN = "AUTH_INVALID_TOKEN"
    AUTH_EXPIRED_TOKEN = "AUTH_EXPIRED_TOKEN"
    AUTH_INSUFFICIENT_PERMISSIONS = "AUTH_INSUFFICIENT_PERMISSIONS"

    # Resource Not Found
    NOTEBOOK_NOT_FOUND = "NOTEBOOK_NOT_FOUND"
    DOCUMENT_NOT_FOUND = "DOCUMENT_NOT_FOUND"
    NOTE_NOT_FOUND = "NOTE_NOT_FOUND"
    TASK_NOT_FOUND = "TASK_NOT_FOUND"
    USER_NOT_FOUND = "USER_NOT_FOUND"
    FEEDBACK_NOT_FOUND = "FEEDBACK_NOT_FOUND"

    # Resource Conflicts
    NOTEBOOK_ALREADY_EXISTS = "NOTEBOOK_ALREADY_EXISTS"
    DOCUMENT_ALREADY_EXISTS = "DOCUMENT_ALREADY_EXISTS"

    # Validation Errors
    VALIDATION_ERROR = "VALIDATION_ERROR"
    INVALID_INPUT = "INVALID_INPUT"
    INPUT_TOO_LONG = "INPUT_TOO_LONG"
    INPUT_TOO_SHORT = "INPUT_TOO_SHORT"
    INVALID_URL = "INVALID_URL"

    # Processing Errors
    PROCESSING_FAILED = "PROCESSING_FAILED"
    DOCUMENT_PROCESSING_FAILED = "DOCUMENT_PROCESSING_FAILED"
    EXTRACTION_FAILED = "EXTRACTION_FAILED"
    CHAT_PROCESSING_FAILED = "CHAT_PROCESSING_FAILED"
    SUGGESTION_FAILED = "SUGGESTION_FAILED"

    # External Service Errors
    EXTERNAL_SERVICE_ERROR = "EXTERNAL_SERVICE_ERROR"
    LLM_PROVIDER_ERROR = "LLM_PROVIDER_ERROR"
    VECTOR_STORE_ERROR = "VECTOR_STORE_ERROR"
    STORAGE_ERROR = "STORAGE_ERROR"

    # Rate Limiting
    RATE_LIMIT_EXCEEDED = "RATE_LIMIT_EXCEEDED"

    # Internal Server Errors
    INTERNAL_ERROR = "INTERNAL_ERROR"
    DATABASE_ERROR = "DATABASE_ERROR"


class ErrorDetail(BaseModel):
    """Detailed error information."""

    code: ErrorCode
    message: str
    field: Optional[str] = None
    details: Optional[Dict[str, Any]] = None


class ErrorResponse(BaseModel):
    """Standardized error response schema."""

    error: ErrorDetail
    request_id: Optional[str] = Field(
        default=None, description="Request ID for tracing"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "error": {
                    "code": "NOTEBOOK_NOT_FOUND",
                    "message": "Notebook not found",
                    "field": "notebook_id",
                }
            }
        }


class ValidationErrorResponse(ErrorResponse):
    """Validation error response with field details."""

    class Config:
        json_schema_extra = {
            "example": {
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": "Validation failed",
                    "field": "message",
                    "details": {"min_length": 1, "max_length": 10000},
                }
            }
        }


# Mapping from HTTP status codes to error codes
HTTP_STATUS_TO_ERROR_CODE: Dict[int, ErrorCode] = {
    400: ErrorCode.INVALID_INPUT,
    401: ErrorCode.AUTH_REQUIRED,
    403: ErrorCode.AUTH_INSUFFICIENT_PERMISSIONS,
    404: ErrorCode.NOTEBOOK_NOT_FOUND,
    409: ErrorCode.NOTEBOOK_ALREADY_EXISTS,
    413: ErrorCode.INPUT_TOO_LONG,
    422: ErrorCode.VALIDATION_ERROR,
    429: ErrorCode.RATE_LIMIT_EXCEEDED,
    500: ErrorCode.INTERNAL_ERROR,
    503: ErrorCode.EXTERNAL_SERVICE_ERROR,
}


def get_error_code_for_status(status_code: int) -> ErrorCode:
    """Get the appropriate error code for an HTTP status code."""
    return HTTP_STATUS_TO_ERROR_CODE.get(status_code, ErrorCode.INTERNAL_ERROR)
