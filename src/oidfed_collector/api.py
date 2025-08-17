# ==============================================================
#       |
#   \  ___  /                           _________
#  _  /   \  _    GÉANT                 |  * *  | Co-Funded by
#     | ~ |       Trust & Identity      | *   * | the European
#      \_/        Incubator             |__*_*__| Union
#       =
# ==============================================================

from typing import Annotated
from fastapi import APIRouter, Query
import logging

from .collection import collect_entities_with_pagination
from .models import EntityCollectionRequest, EntityCollectionResponse
from .session_manager import SessionManager
from .config import CONFIG

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get(
    path="/",
    name="Entity collection",
    description="Collect all entities",
    response_description="Entity collection response",
    response_model_exclude_none=True,
    response_model_exclude_unset=True,
)
async def collection(
    request: Annotated[EntityCollectionRequest, Query()],
):
    session_mgr = SessionManager(
        ttl_seconds=CONFIG.session.ttl,
        max_connections=CONFIG.session.max_concurrent_requests,
    )
    response = await collect_entities_with_pagination(request, session_mgr)
    await session_mgr.close()
    if isinstance(response, EntityCollectionResponse):
        # Convert to dict with language support
        response = response.to_dict(lang=request.lang)
    return response
