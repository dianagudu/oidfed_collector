import logging
import time
from typing import Optional, Tuple, List
import asyncio

from .models import (
    Entity,
    EntityStatementPlus,
    EntityCollectionRequest,
    EntityCollectionResponse,
)
from .utils import get_entity_configuration, get_list_subordinate_ids
from .session_manager import SessionManager
from .cache import async_cache


logger = logging.getLogger(__name__)


class EntityFilter:
    def __init__(self, request: EntityCollectionRequest) -> None:
        self.entity_type = request.entity_type
        self.trust_mark_type = request.trust_mark_type
    
    def _filter(self, entity: EntityStatementPlus) -> bool:
        """Filters the entity based on the provided filters.
        
        :param entity: The entity to filter.
        :type entity: EntityStatementPlus
        :return: True if the entity matches the filters, False otherwise.
        """
        if self.entity_type:
            md = entity.get("metadata")
            if not md:
                logger.debug("No metadata found in entity statement, skipping entity.")
                return False
            else:
                if not any(
                    et in md.keys() for et in self.entity_type
                ):
                    logger.debug(
                        f"Entity {entity.get('sub')} does not match entity type filter {self.entity_type}, skipping."
                    )
                    return False
                
    
        if self.trust_mark_type:
            tms = entity.get("trust_marks")
            logger.debug("Trust marks: %s", tms)
            if not tms:
                logger.debug("No trust marks found in entity statement, skipping entity.")
                return False
            else:
                trust_marks = [tm.get("trust_mark_type") or tm.get("trust_mark_id") for tm in tms]
                # todo validate each trust mark
                if not any(
                    tm in trust_marks
                    for tm in self.trust_mark_type
                ):
                    logger.debug(
                        f"Entity {entity.get('sub')} does not match trust mark type filter {self.trust_mark_type}, skipping."
                    )
                    return False

        return True
    
    def apply(self, entities: list[EntityStatementPlus]) -> list[Entity]:
        """Applies the filters to the list of entities.
        
        :param entities: The list of entities to filter.
        :type entities: list[EntityStatementPlus]
        :return: A list of filtered entities.
        """
        return [entity.to_entity() for entity in entities if self._filter(entity)]


class FedTree:
    def __init__(self, entity: EntityStatementPlus) -> None:
        logger.debug("Processing node: %s", entity.get("sub"))
        self.entity = entity
        self.subordinates = []

    def flatten(self) -> list[EntityStatementPlus]:
        """Returns a list of entities contained in the FedTree.
        
        :return: A list of entity statement objects.
        :rtype: list[EntityStatementPlus]
        """
        entities = [self.entity]
        for sub in self.subordinates:
            entities += sub.flatten()
        return entities


@async_cache(ttl=60, key_func=lambda root, *args, **kwargs: root)
async def traverse(root: str, visited: list[str], session_mgr: SessionManager) -> Tuple[Optional[FedTree], int]:
    """Traverses the federation tree starting from the given root entity ID.
    
    :param root: The entity ID of the root entity.
    :type root: str
    :param visited: A list of already visited entity IDs to avoid cycles.
    :type visited: list[str]
    :param session_mgr: The session manager to use for HTTP requests.
    :type session_mgr: SessionManager
    :return: A tuple containing the federation tree and the last updated timestamp.
    :rtype: Tuple[Optional[FedTree], int]
    """
    try:
        logger.debug(f"Traversing entity: {root}")
        
        ta = await get_entity_configuration(entity_id=root, session_mgr=session_mgr)
        subs_ids = await get_list_subordinate_ids(ta, session_mgr=session_mgr)

        tree = FedTree(entity=ta)
        
        tasks = []
        for sub_id in subs_ids:
            if sub_id in visited:
                logger.debug(f"Already visited {sub_id}, skipping to avoid cycles.")
                continue
            visited.append(sub_id)
            tasks.append(traverse(root=sub_id, visited=visited, session_mgr=session_mgr))

        if tasks:
            results = await asyncio.gather(*tasks)
            tree.subordinates = [sub for sub, _ in results if sub is not None]

        return tree, int(time.time())
    except Exception as e:
        logger.warning(f"Could not traverse entity {root}: {e}")
        return None, int(time.time())


async def collect_entities(request: EntityCollectionRequest, session_mgr: SessionManager) -> EntityCollectionResponse:
    """Collects entities based on the provided request and session manager.
    :param request: The request containing filters and parameters for entity collection.
    :type request: EntityCollectionRequest
    :param session_mgr: The session manager to use for HTTP requests.
    :type session_mgr: SessionManager
    :return: An EntityCollectionResponse containing the collected entities.
    :rtype: EntityCollectionResponse
    """
    tree, last_updated = await traverse(request.trust_anchor.encoded_string(), visited=[], session_mgr=session_mgr)

    if not tree:
        logger.warning("No entities found in the federation tree.")
        return EntityCollectionResponse(entities=[], last_updated=last_updated)

    entities = tree.flatten()


    filters = EntityFilter(request)
    filtered_entities = filters.apply(entities)

    return EntityCollectionResponse(
        entities=filtered_entities,
        last_updated=last_updated
    )