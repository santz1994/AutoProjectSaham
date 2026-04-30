"""
Error Handler Middleware for FastAPI

Centralized exception handling that:
1. Catches all exceptions
2. Converts to user-friendly error responses
3. Logs errors with correlation IDs
4. Maps HTTP status codes appropriately

Usage in server.py:
    from src.api.error_handler import setup_error_handlers
    
    app = FastAPI()
    setup_error_handlers(app)
"""
from __future__ import annotations

import traceback
from typing import Union
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from src.utils.exceptions import (
    AutoSahamError,
    UserError,
    SystemError,
    ExternalAPIError,
    handle_exception
)
from src.utils.logger import get_logger, set_correlation_id, get_correlation_id

logger = get_logger(__name__)


async def autosaham_exception_handler(
    request: Request,
    exc: AutoSahamError
) -> JSONResponse:
    """
    Handle AutoSaham custom exceptions.
    
    Args:
        request: FastAPI request
        exc: AutoSaham exception
        
    Returns:
        JSON error response
    """
    # Set correlation ID from request header or generate new
    correlation_id = request.headers.get('X-Correlation-ID') or set_correlation_id()
    
    # Determine HTTP status code
    if isinstance(exc, UserError):
        status_code = status.HTTP_400_BAD_REQUEST
    elif isinstance(exc, SystemError):
        status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    elif isinstance(exc, ExternalAPIError):
        status_code = status.HTTP_502_BAD_GATEWAY
    else:
        status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    
    # Log error
    logger.error(
        f"AutoSaham error: {exc.message}",
        extra={
            'error_code': exc.code,
            'error_type': exc.__class__.__name__,
            'path': str(request.url),
            'method': request.method
        },
        exc_info=True
    )
    
    # Build response
    error_dict = exc.to_dict()
    error_dict['correlation_id'] = correlation_id
    error_dict['path'] = str(request.url)
    
    return JSONResponse(
        status_code=status_code,
        content={'error': error_dict}
    )


async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError
) -> JSONResponse:
    """
    Handle Pydantic validation errors.
    
    Args:
        request: FastAPI request
        exc: Validation error
        
    Returns:
        JSON error response
    """
    correlation_id = request.headers.get('X-Correlation-ID') or set_correlation_id()
    
    # Extract validation errors
    errors = []
    for error in exc.errors():
        errors.append({
            'field': '.'.join(str(loc) for loc in error['loc']),
            'message': error['msg'],
            'type': error['type']
        })
    
    logger.warning(
        f"Validation error on {request.url.path}",
        extra={
            'validation_errors': errors,
            'path': str(request.url),
            'method': request.method
        }
    )
    
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            'error': {
                'error_type': 'ValidationError',
                'message': 'Request validation failed',
                'validation_errors': errors,
                'correlation_id': correlation_id,
                'path': str(request.url)
            }
        }
    )


async def http_exception_handler(
    request: Request,
    exc: StarletteHTTPException
) -> JSONResponse:
    """
    Handle HTTP exceptions.
    
    Args:
        request: FastAPI request
        exc: HTTP exception
        
    Returns:
        JSON error response
    """
    correlation_id = request.headers.get('X-Correlation-ID') or set_correlation_id()
    
    logger.warning(
        f"HTTP {exc.status_code}: {exc.detail}",
        extra={
            'status_code': exc.status_code,
            'path': str(request.url),
            'method': request.method
        }
    )
    
    return JSONResponse(
        status_code=exc.status_code,
        content={
            'error': {
                'error_type': 'HTTPException',
                'message': exc.detail,
                'status_code': exc.status_code,
                'correlation_id': correlation_id,
                'path': str(request.url)
            }
        }
    )


async def general_exception_handler(
    request: Request,
    exc: Exception
) -> JSONResponse:
    """
    Handle all other exceptions.
    
    Args:
        request: FastAPI request
        exc: Any exception
        
    Returns:
        JSON error response
    """
    correlation_id = request.headers.get('X-Correlation-ID') or set_correlation_id()
    
    # Log full traceback
    logger.error(
        f"Unhandled exception: {exc}",
        extra={
            'exception_type': exc.__class__.__name__,
            'path': str(request.url),
            'method': request.method,
            'traceback': traceback.format_exc()
        },
        exc_info=True
    )
    
    # Convert to standard error format
    error_dict = handle_exception(exc)
    error_dict['correlation_id'] = correlation_id
    error_dict['path'] = str(request.url)
    
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={'error': error_dict}
    )


def setup_error_handlers(app: FastAPI) -> None:
    """
    Setup all error handlers for FastAPI app.
    
    Args:
        app: FastAPI application instance
    """
    # AutoSaham custom exceptions
    app.add_exception_handler(AutoSahamError, autosaham_exception_handler)
    
    # Validation errors
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    
    # HTTP exceptions
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    
    # Catch-all for any other exceptions
    app.add_exception_handler(Exception, general_exception_handler)
    
    logger.info("Error handlers configured")


# Middleware to add correlation ID to all requests
async def correlation_id_middleware(request: Request, call_next):
    """Add correlation ID to request context."""
    # Get or generate correlation ID
    correlation_id = request.headers.get('X-Correlation-ID') or set_correlation_id()
    
    # Process request
    response = await call_next(request)
    
    # Add correlation ID to response headers
    response.headers['X-Correlation-ID'] = correlation_id
    
    return response


# Example usage
if __name__ == "__main__":
    from fastapi import FastAPI
    from src.utils.exceptions import CommonErrors
    
    app = FastAPI()
    setup_error_handlers(app)
    
    @app.get("/test/user-error")
    async def test_user_error():
        """Test user error handling."""
        raise CommonErrors.invalid_symbol("INVALID")
    
    @app.get("/test/system-error")
    async def test_system_error():
        """Test system error handling."""
        raise CommonErrors.model_not_found("models/missing.joblib")
    
    @app.get("/test/validation-error")
    async def test_validation(value: int):
        """Test validation error handling."""
        return {"value": value}
    
    @app.get("/test/general-error")
    async def test_general_error():
        """Test general error handling."""
        raise ValueError("Something went wrong!")
    
    print("Test endpoints registered:")
    print("  GET /test/user-error")
    print("  GET /test/system-error")
    print("  GET /test/validation-error?value=abc")
    print("  GET /test/general-error")
    print("\nRun with: uvicorn src.api.error_handler:app")
