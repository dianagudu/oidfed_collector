# ==============================================================
#       |
#   \  ___  /                           _________
#  _  /   \  _    GÉANT                 |  * *  | Co-Funded by
#     | ~ |       Trust & Identity      | *   * | the European
#      \_/        Incubator             |__*_*__| Union
#       =
# ==============================================================

from pydantic import ValidationError
from fastapi import Request
from fastapi.exceptions import (
    HTTPException,
    RequestValidationError,
    ResponseValidationError,
)
from fastapi.responses import JSONResponse
from starlette.status import (
    HTTP_400_BAD_REQUEST,
    HTTP_401_UNAUTHORIZED,
    HTTP_404_NOT_FOUND,
    HTTP_500_INTERNAL_SERVER_ERROR,
)

import logging

from oidfed_collector import message

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class BadRequest(JSONResponse):
    """Response for invalid request."""

    def __init__(self, error_code: str, message: str | None = None):
        super().__init__(
            status_code=HTTP_400_BAD_REQUEST,
            content={"error_code": error_code, "message": message},
        )


class NotFound(JSONResponse):
    """Response for not found resources.

    Returns HTTP 404 Not Found status code
    and informative message.
    """

    def __init__(self, error_code: str):
        super().__init__(
            status_code=HTTP_404_NOT_FOUND, content={"error_code": error_code}
        )


class InvalidResponse(JSONResponse):
    """Response for invalid response model.

    Returns HTTP 500 Internal Server Error status code
    and informative message.
    """

    def __init__(self, exc: ResponseValidationError | ValidationError):
        message = "Could not validate response model."
        _ = exc
        super().__init__(
            status_code=HTTP_500_INTERNAL_SERVER_ERROR,
            content={"error_code": "invalid_response", "message": message},
        )


class InternalException(Exception):
    """Wrapper for internal errors"""

    def __init__(self, message) -> None:
        self.message = message
        super().__init__(message)


async def request_validation_exception_handler(
    request: Request, exc: Exception
) -> JSONResponse:
    """Replacement callback for handling RequestValidationError exceptions.

    :param request: request object that caused the RequestValidationError
    :param exc: Exception containing validation errors
    """
    _ = request
    logger.debug(exc)
    if isinstance(exc, RequestValidationError):
        if any(err.get("type") == "missing" for err in exc.errors()):
            return BadRequest(
                error_code="invalid_request",
                message="Missing required parameter(s): %s"
                % ", ".join(
                    err["loc"][-1]
                    for err in exc.errors()
                    if err.get("type") == "missing"
                ),
            )
        elif any(err.get("type") == "extra_forbidden" for err in exc.errors()):
            return BadRequest(
                error_code="unsupported_parameter",
                message="Unsupported parameter(s): %s"
                % ", ".join(
                    err["loc"][-1]
                    for err in exc.errors()
                    if err.get("type") == "extra_forbidden"
                ),
            )
    return BadRequest(error_code="invalid_request")


async def response_validation_exception_handler(request: Request, exc: Exception):
    """Replacement callback for handling ResponseValidationError exceptions.

    :param request: request object that caused the ResponseValidationError
    :param validation_exc: ResponseValidationError containing validation errors
    """
    _ = request
    _ = exc
    return (
        InvalidResponse(exc)
        if isinstance(exc, (ResponseValidationError, ValidationError))
        else JSONResponse(
            status_code=HTTP_500_INTERNAL_SERVER_ERROR, content={"detail": str(exc)}
        )
    )
