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

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class BadRequest(JSONResponse):
    """Response for invalid request."""

    def __init__(self, message: str):
        super().__init__(status_code=HTTP_400_BAD_REQUEST, content={"detail": message})


class MissingParameter(JSONResponse):
    """Response for missing query parameters.

    Returns HTTP 400 Bad Request status code
    and informative message.
    """

    def __init__(self, exc: RequestValidationError):
        errors = exc.errors()
        no_errors = len(errors)
        message = (
            f"{no_errors} request validation error{'' if no_errors == 1 else 's'}: "
            + "; ".join(
                f"{e['msg']} ({(' -> '.join(str(l) for l in e['loc']))})"
                for e in errors
            )
        )
        super().__init__(status_code=HTTP_400_BAD_REQUEST, content={"detail": message})


class InvalidResponse(JSONResponse):
    """Response for invalid response model.

    Returns HTTP 500 Internal Server Error status code
    and informative message.
    """

    def __init__(self, exc: ResponseValidationError | ValidationError):
        message = "Could not validate response model."
        _ = exc
        super().__init__(
            status_code=HTTP_500_INTERNAL_SERVER_ERROR, content={"detail": message}
        )


class InternalException(Exception):
    """Wrapper for internal errors"""

    def __init__(self, message) -> None:
        self.message = message
        super().__init__(message)


async def request_validation_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Replacement callback for handling RequestValidationError exceptions.

    :param request: request object that caused the RequestValidationError
    :param exc: Exception containing validation errors
    """
    _ = request
    logger.debug(exc)
    if isinstance(exc, RequestValidationError):
        return MissingParameter(exc)
    return BadRequest(exc.__str__())


async def validation_exception_handler(
    request: Request, exc: Exception
):
    """Replacement callback for handling ResponseValidationError exceptions.

    :param request: request object that caused the ResponseValidationError
    :param validation_exc: ResponseValidationError containing validation errors
    """
    _ = request
    _ = exc
    return InvalidResponse(exc) if isinstance(exc, (ResponseValidationError, ValidationError)) else JSONResponse(
        status_code=HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": str(exc)}
    )