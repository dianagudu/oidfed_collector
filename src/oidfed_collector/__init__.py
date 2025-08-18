# ==============================================================
#       |
#   \  ___  /                           _________
#  _  /   \  _    GÉANT                 |  * *  | Co-Funded by
#     | ~ |       Trust & Identity      | *   * | the European
#      \_/        Incubator             |__*_*__| Union
#       =
# ==============================================================

__name__ = "oidfed_collector"

import subprocess
import os
from ._version import __version__ as _version_placeholder

__version__ = _version_placeholder

# Runtime: try to get git tag if still placeholder
if _version_placeholder == "0.0.0":
    try:
        # Prefer the tag from GitHub Actions if available
        tag = os.getenv("GITHUB_REF_NAME")
        if tag:
            git_version = tag.lstrip("v")
        else:
            git_version = (
                subprocess.check_output(
                    ["git", "describe", "--tags", "--always"],
                    stderr=subprocess.DEVNULL,
                )
                .decode()
                .strip()
                .lstrip("v")
            )
        if git_version:
            __version__ = git_version
    except Exception:
        pass

__all__ = ["__version__"]

import logging
import logging.handlers
import sys
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError, ResponseValidationError
from contextlib import asynccontextmanager

from .config import CONFIG
from .exceptions import (
    request_validation_exception_handler,
    response_validation_exception_handler,
)
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

    app.add_exception_handler(
        RequestValidationError, request_validation_exception_handler
    )
    app.add_exception_handler(
        ResponseValidationError, response_validation_exception_handler
    )
    app.include_router(
        api_router, prefix=CONFIG.api_base_url, tags=["Entity Collection"]
    )

    # configure logging
    if CONFIG.log_file is None or CONFIG.log_file == "/dev/stderr":
        log_handler = logging.StreamHandler()
    elif CONFIG.log_file == "/dev/stdout":
        log_handler = logging.StreamHandler(sys.stdout)
    else:
        try:
            log_handler = logging.handlers.RotatingFileHandler(
                CONFIG.log_file, maxBytes=100**6, backupCount=2
            )
        except Exception:  # pylint: disable=broad-except
            # anything goes wrong, fallback to stderr
            log_handler = logging.StreamHandler()
    log_format = "[%(asctime)s] [%(name)s] %(levelname)s - %(message)s"
    logging.basicConfig(
        level=CONFIG.log_level.upper(),
        handlers=[log_handler],
        format=log_format,
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    return app


app = create_app()
