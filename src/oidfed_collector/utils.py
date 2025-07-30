import logging
from typing import Tuple

from .exceptions import InternalException
from .models import URL, EntityStatementPlus
from .cache import async_cache, my_cache
from .session_manager import SessionManager

logger = logging.getLogger(__name__)


@async_cache(
    ttl_func=lambda result, *args, **kwargs: result._ttl,
    key_func=lambda entity_id, *args, **kwargs: entity_id,
    cache=my_cache,  # Use the global cache instance
)
async def get_entity_configuration(entity_id: str, session_mgr: SessionManager) -> EntityStatementPlus:
    """Fetches the entity configuration of a given entity ID.
    :param entity_id: The entity ID to fetch the entity configuration from (string).
    :return: The entity configuration as an EntityStatementPlus object.
    """
    url = URL(entity_id).remove_trailing_slashes() + "/.well-known/openid-federation"
    async with session_mgr as session:
        async with session.get(url) as resp:
            if resp.status != 200:
                raise InternalException(
                    "Could not fetch entity configuration from %s. Status code: %s"
                    % (entity_id, resp.status)
                )
            return EntityStatementPlus(await resp.text())


# use ttl function and cache for as long as the entity configuration is valid
@async_cache(
    ttl_func=lambda result, *args, **kwargs: result[1],
    key_func=lambda url, *args, **kwargs: url,
    cache=my_cache
)
async def cached_get_list(url: str, session_mgr: SessionManager, ttl_ec: float | None) -> Tuple[dict, float | None]:
    """Fetches a URL and caches the result.
    
    :param url: The URL to fetch.
    :return: The JSON response from the URL and the TTL of the entity configuration.
    :rtype: Tuple[dict, float | None]
    """
    async with session_mgr as session:
        async with session.get(url) as resp:
            if resp.status != 200:
                raise InternalException(f"Failed to fetch {url}. Status code: {resp.status}")
            return await resp.json(), ttl_ec


async def get_list_subordinate_ids(
    entity: EntityStatementPlus,
    session_mgr: SessionManager
) -> list[str]:
    """Fetches the subordinates of a given entity.

    :param entity: The entity to fetch the subordinates from.
    :return: A list of subordinate entity IDs.
    """
    try:
        metadata = entity.get("metadata")
        if not metadata:
            raise InternalException("No metadata found in entity configuration.")
        try:
            le = metadata["federation_entity"]
        except KeyError:
            raise InternalException("Leaf entities cannot have subordinates.")
        try:
            list_url = le["federation_list_endpoint"]
        except KeyError:
            raise InternalException("No federation_list_endpoint found in metadata!")

        subs, _ = await cached_get_list(list_url, session_mgr=session_mgr, ttl_ec=entity._ttl)

        # sort list of strings to ensure consistent order
        return sorted(list(subs))
    except Exception as e:
        logger.debug(f"Could not fetch subordinates for {entity.get('sub')}: {e}")
        return []
