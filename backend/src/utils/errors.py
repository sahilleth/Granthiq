"""
Error handling utilities for standardized error responses.
"""

from typing import Optional, Any, Dict
from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from loguru import logger
import uuid

from src.schemas.error import (
    ErrorCode,
    ErrorResponse,
    ErrorDetail,
    get_error_code_for_status,
)


class AppHTTPException(HTTPException):
    """
    Extended HTTPException with standardized error codes.

    Example:
        raise AppHTTPException(
            status_code=404,
            code=ErrorCode.NOTEBOOK_NOT_FOUND,
            message="Notebook not found",
            field="notebook_id"
        )
    """

    def __init__(
        self,
        status_code: int,
        code: Optional[ErrorCode] = None,
        message: Optional[str] = None,
        field: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        self.code = code or get_error_code_for_status(status_code)
        self.message = message or self.code.value.replace("_", " ").title()
        self.field = field
        self.details = details
        super().__init__(status_code=status_code, detail=self.message)


async def error_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """
    Custom exception handler that formats all HTTPExceptions with standardized error response.
    """
    request_id = str(uuid.uuid4())

    # Get the error code
    if isinstance(exc, AppHTTPException):
        code = exc.code
        message = exc.message
        field = exc.field
        details = exc.details
    else:
        code = get_error_code_for_status(exc.status_code)
        message = exc.detail
        field = None
        details = None

    error_detail = ErrorDetail(
        code=code,
        message=message,
        field=field,
        details=details,
    )

    logger.warning(
        f"Request error: {request_id} | {code.value} | {message} | {request.url.path}"
    )

    return JSONResponse(
        status_code=exc.status_code,
        content=ErrorResponse(
            error=error_detail,
            request_id=request_id,
        ).model_dump(),
    )


def create_error_response(
    status_code: int,
    code: ErrorCode,
    message: str,
    field: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
) -> JSONResponse:
    """Create a standardized error JSONResponse."""
    error_detail = ErrorDetail(
        code=code,
        message=message,
        field=field,
        details=details,
    )

    return JSONResponse(
        status_code=status_code,
        content=ErrorResponse(
            error=error_detail,
            request_id=str(uuid.uuid4()),
        ).model_dump(),
    )
