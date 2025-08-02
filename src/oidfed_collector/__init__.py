# ==============================================================
#       |
#   \  ___  /                           _________
#  _  /   \  _    GÉANT                 |  * *  | Co-Funded by
#     | ~ |       Trust & Identity      | *   * | the European
#      \_/        Incubator             |__*_*__| Union
#       =
# ==============================================================

__name__ = "oidfed_collector"

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError, ResponseValidationError
from contextlib import asynccontextmanager

from ._version import __version__
from .config import CONFIG
from .exceptions import request_validation_exception_handler, validation_exception_handler
from .api import router as api_router
from .cache import my_cache

def create_app():
    """Create the FastAPI app."""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        await my_cache.start()
        yield
        await my_cache.stop()

    app = FastAPI(
        title="OIDFed Collection",
        description="REST API for entity collection spec",
        version=__version__,
        docs_url="/docs",
        lifespan=lifespan,
    )

    app.add_exception_handler(RequestValidationError, request_validation_exception_handler)
    app.add_exception_handler(ResponseValidationError, validation_exception_handler)
    app.include_router(api_router, prefix=CONFIG.api_base_url, tags=["Entity Collection"])

    return app

app = create_app()

