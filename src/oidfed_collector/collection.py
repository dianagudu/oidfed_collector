# ==============================================================
#       |
#   \  ___  /                           _________
#  _  /   \  _    GÉANT                 |  * *  | Co-Funded by
#     | ~ |       Trust & Identity      | *   * | the European
#      \_/        Incubator             |__*_*__| Union
#       =
# ==============================================================

import logging
import re
import time
from typing import Optional, Tuple
import asyncio
import copy

from oidfed_collector.exceptions import NotFound


from .config import CONFIG
from .message import TrustMark
from .models import (
    Entity,
    EntityStatementPlus,
    EntityCollectionRequest,
    EntityCollectionResponse,
    UiInfo,
    get_payload,
    URL,
)
from .utils import get_entity_configuration, get_list_subordinate_ids, hash_request
from .session_manager import SessionManager
from .cache import async_cache, my_cache


logger = logging.getLogger(__name__)


class EntityFilter:
    def __init__(self, request: EntityCollectionRequest) -> None:
        self.entity_type = request.entity_type
        self.trust_mark_type = request.trust_mark_type
        self.entity_claims = request.entity_claims
        self.ui_claims = request.ui_claims

        logger.debug("Applying filters: %s", request)

    def _filter(self, entity: EntityStatementPlus) -> Entity | None:
        """Filters the entity based on the provided filters and returns the entity
        in the format specified by the Entity model.
        The entity must match all filters and will return None if it does not match.
        The filter also filters out specific claims, if provided in the request.

        :param entity: The entity to filter.
        :type entity: EntityStatementPlus
        :return: The filtered entity if it matches the filters, None otherwise.
        """
        md = entity.get("metadata")
        if not md:
            logger.debug("No metadata found in entity statement, skipping entity.")
            return None

        if self.entity_type:
            # check if any of the entity types in the metadata match the requested entity types
            if not any(et in md.keys() for et in self.entity_type):
                logger.debug(
                    f"Entity {entity.get('sub')} does not match entity type filter {self.entity_type}, skipping."
                )
                return None

        tms = entity.get(
            "trust_marks"
        )  # array of json objects with trust_mark_type and trust_mark
        if self.trust_mark_type:
            if not tms:
                logger.debug(
                    "No trust marks found in entity statement, skipping entity."
                )
                return None

            # check if the entity contains all requested trust mark types
            if not all(
                tm in (t.get("trust_mark_type", t.get("trust_mark_id")) for t in tms)
                for tm in self.trust_mark_type
            ):
                logger.debug(
                    f"Entity {entity.get('sub')} does not match trust mark type filter {self.trust_mark_type}, skipping."
                )
                return None
            # validate each of the required trust marks
            required_tms = [
                tm.get("trust_mark")
                for tm in tms
                if tm.get("trust_mark_type", tm.get("trust_mark_id"))
                in self.trust_mark_type
            ]
            try:
                if not all(
                    TrustMark(**get_payload(tm)).verify() for tm in required_tms
                ):
                    logger.debug(
                        f"Entity {entity.get('sub')} has invalid trust marks, skipping."
                    )
                    return None
            except ValueError as e:
                logger.debug(
                    f"Entity {entity.get('sub')} has invalid trust marks: {e}, skipping."
                )
                return None

        entity_dict = {}
        entity_dict["entity_id"] = entity.get("sub")
        entity_dict["entity_types"] = entity.get_entity_types()
        entity_dict["trust_marks"] = (
            [
                {
                    "trust_mark_type": tm.get(
                        "trust_mark_type", tm.get("trust_mark_id")
                    ),
                    "trust_mark": tm.get("trust_mark"),
                }
                for tm in tms
            ]
            if tms
            else None
        )

        entity_dict["ui_infos"] = None

        # if entity_types is provided, use it to filter the UI infos
        # otherwise, use all entity types in the metadata
        for etype in (
            set(self.entity_type + ["federation_entity"])
            if self.entity_type
            else entity_dict["entity_types"]
        ):
            md_type = md.get(etype)
            if md_type:
                display_name = md_type.get("display_name", None)
                if not display_name:
                    if etype == "openid_relying_party" or etype == "oauth_client":
                        display_name = md_type.get("client_name", None)
                    elif etype == "oauth_resource":
                        display_name = md_type.get("resource_name", None)

                ui_info_dict = {}
                ui_info_dict["display_name"] = display_name
                ui_info_dict["description"] = md_type.get("description", None)
                ui_info_dict["keywords"] = md_type.get("keywords", None)
                ui_info_dict["logo_uri"] = md_type.get("logo_uri", None)
                ui_info_dict["policy_uri"] = md_type.get("policy_uri", None)
                ui_info_dict["information_uri"] = md_type.get("information_uri", None)

                # check for language tags (start with claim_name#) in metadata for all claims in UI info and add them to the UI info
                for k, v in md_type.items():
                    if (
                        k.startswith("display_name#")
                        or k.startswith("description#")
                        or k.startswith("keywords#")
                        or k.startswith("logo_uri#")
                        or k.startswith("policy_uri#")
                        or k.startswith("information_uri#")
                    ):
                        ui_info_dict[k] = v

                # only set if there is at least one entry in the UI info dict that is not None
                if any(v is not None for v in ui_info_dict.values()):
                    if entity_dict["ui_infos"] is None:
                        entity_dict["ui_infos"] = {}
                    # filter UI infos by ui_claims, if provided
                    entity_dict["ui_infos"][etype] = UiInfo(
                        **{
                            k: v
                            for k, v in ui_info_dict.items()
                            if not self.ui_claims or k in self.ui_claims
                        }
                    )

        # filter by entity_claims, if provided
        return Entity(
            **{
                k: v
                for k, v in entity_dict.items()
                if not self.entity_claims
                or k in set(self.entity_claims + ["entity_id"])
            }
        )

    def apply(self, entities: list[EntityStatementPlus]) -> list[Entity]:
        """Applies the filters to the list of entities.

        :param entities: The list of entities to filter.
        :type entities: list[EntityStatementPlus]
        :return: A list of filtered entities.
        """
        logger.debug("Applying filters to %d entities", len(entities))
        filtered_entities = [self._filter(entity) for entity in entities]
        filtered_entities = [e for e in filtered_entities if e is not None]
        logger.debug("Filtered entities: %d", len(filtered_entities))
        return filtered_entities


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


@async_cache(
    ttl=CONFIG.cache.ttl, key_func=lambda root, *args, **kwargs: root, cache=my_cache
)
async def traverse(
    root: str, visited: list[str], session_mgr: SessionManager
) -> Tuple[Optional[FedTree], int]:
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
            tasks.append(
                traverse(root=sub_id, visited=visited, session_mgr=session_mgr)
            )

        if tasks:
            results = await asyncio.gather(*tasks)
            tree.subordinates = [sub for sub, _ in results if sub is not None]

        return tree, int(time.time())
    except Exception as e:
        logger.warning(f"Could not traverse entity {root}: {e}")
        return None, int(time.time())


@async_cache(ttl=CONFIG.cache.ttl, key_func=hash_request, cache=my_cache)
async def collect_entities(
    request: EntityCollectionRequest, session_mgr: SessionManager
) -> EntityCollectionResponse:
    """Collects entities based on the provided request and session manager.
    :param request: The request containing filters and parameters for entity collection.
    :type request: EntityCollectionRequest
    :param session_mgr: The session manager to use for HTTP requests.
    :type session_mgr: SessionManager
    :return: An EntityCollectionResponse containing the collected entities.
    :rtype: EntityCollectionResponse
    """
    trust_anchor = URL(request.trust_anchor).remove_trailing_slashes()
    tree, last_updated = await traverse(
        str(trust_anchor), visited=[str(trust_anchor)], session_mgr=session_mgr
    )

    if not tree:
        logger.warning("No entities found in the federation tree.")
        return EntityCollectionResponse(entities=[], last_updated=last_updated)

    entities = tree.flatten()

    filters = EntityFilter(request)
    filtered_entities = filters.apply(entities)

    return EntityCollectionResponse(
        entities=filtered_entities, last_updated=last_updated
    )


async def collect_entities_with_pagination(
    request: EntityCollectionRequest, session_mgr: SessionManager
) -> EntityCollectionResponse | NotFound:
    """Collects entities with pagination support based on the provided request and session manager.
    :param request: The request containing filters and parameters for entity collection.
    :type request: EntityCollectionRequest
    :param session_mgr: The session manager to use for HTTP requests.
    :type session_mgr: SessionManager
    :return: An EntityCollectionResponse containing the collected entities.
    :rtype: EntityCollectionResponse
    """
    # if this is a subsequent request of a paginated response
    if request.from_entity_id is not None:
        # check if response can be found in the cache
        cached_response = await my_cache.get(hash_request(request))
        if not cached_response:
            logger.error(
                f"No cached response found for {request.from_entity_id} with limit {request.limit}"
            )
            # todo: return 404 application/json with error code entity_id_not_found
            return NotFound(error_code="entity_id_not_found")
        else:
            logging.debug("Using cached response for paginated request.")
            start_index = next(
                (
                    i
                    for i, e in enumerate(cached_response.entities)
                    if URL(e.entity_id).remove_trailing_slashes()
                    == URL(request.from_entity_id).remove_trailing_slashes()
                ),
                None,
            )
            if start_index is None:
                logger.error(
                    f"Entity ID {request.from_entity_id} not found in cached response."
                )
                return NotFound(error_code="entity_id_not_found")
            logger.debug(
                f"Starting from entity index {start_index} in cached response, which has {len(cached_response.entities)} entities."
            )
            response = copy.deepcopy(cached_response)
            response.entities = copy.deepcopy(
                cached_response.entities[start_index + 1 :]
            )
    else:  # if this is the first request
        # collect all entities without pagination
        response = copy.deepcopy(await collect_entities(request, session_mgr))

    # if limit is set, apply it to the response
    if request.limit is not None:
        # return only the requested number of entities
        response.entities = copy.deepcopy(response.entities[: request.limit])
        if len(response.entities) < request.limit:
            response.next_entity_id = None
        else:
            response.next_entity_id = URL(
                response.entities[-1].entity_id
            ).remove_trailing_slashes()
    else:
        response.next_entity_id = None
    return response
