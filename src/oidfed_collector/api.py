from typing import Annotated
from fastapi import APIRouter, Query
import logging

from .collection import collect_entities
from .models import EntityCollectionRequest, EntityCollectionResponse
from .session_manager import SessionManager
from .config import CONFIG

router = APIRouter()
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


@router.get(
    path="/",
    name="Entity collection",
    description="Collect all entities",
    response_description="Entity collection response",
    response_model_exclude_none=True,
    response_model_exclude_unset=True,
)
async def collection(request: Annotated[EntityCollectionRequest, Query()]) -> EntityCollectionResponse:
    session_mgr = SessionManager(
        ttl_seconds=CONFIG.session.ttl,
        max_connections=CONFIG.session.max_concurrent_requests
    )
    entities = await collect_entities(request, session_mgr)
    await session_mgr.close()
    return entities
