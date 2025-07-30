import time
import asyncio
from cachetools import LRUCache
from functools import wraps
from typing import Callable, Any, Optional
import logging
import contextlib

from .config import CONFIG


logger = logging.getLogger(__name__)

class AsyncTTLCacheWithEviction:
    def __init__(self, maxsize=1024, cleanup_interval=60):
        self._cache = LRUCache(maxsize=maxsize)
        self._lock = asyncio.Lock()
        self._cleanup_interval = cleanup_interval
        self._cleanup_task = None

    def _normalize_key(self, key):
        if not hasattr(key, '__hash__'):
            raise TypeError(f"Unhashable key: {key}")
        return key

    async def set(self, key, value, ttl=None):
        key = self._normalize_key(key)
        expires_at = time.time() + ttl if ttl else None
        async with self._lock:
            self._cache[key] = (value, expires_at)

    async def get(self, key, default=None):
        key = self._normalize_key(key)
        async with self._lock:
            item = self._cache.get(key)
            if not item:
                return default
            value, expires_at = item
            if expires_at and time.time() > expires_at:
                del self._cache[key]
                return default
            return value

    async def has(self, key):
        key = self._normalize_key(key)
        async with self._lock:
            item = self._cache.get(key)
            if not item:
                return False
            _, expires_at = item
            if expires_at and time.time() > expires_at:
                del self._cache[key]
                return False
            return True

    async def delete(self, key):
        key = self._normalize_key(key)
        async with self._lock:
            self._cache.pop(key, None)

    async def clear(self):
        async with self._lock:
            self._cache.clear()

    async def size(self):
        async with self._lock:
            return sum(
                1 for _, exp in self._cache.values()
                if exp is None or exp > time.time()
            )

    async def start(self):
        if self._cleanup_task is None:
            self._cleanup_task = asyncio.create_task(self._background_cleanup())

    async def _background_cleanup(self):
        try:
            while True:
                await asyncio.sleep(self._cleanup_interval)
                now = time.time()
                async with self._lock:
                    keys_to_delete = [k for k, (_, exp) in self._cache.items()
                                      if exp is not None and exp < now]
                    for k in keys_to_delete:
                        del self._cache[k]
        except asyncio.CancelledError:
            pass

    async def stop(self):
        if self._cleanup_task:
            self._cleanup_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._cleanup_task
            self._cleanup_task = None


def async_cache(ttl: Optional[float] = None,
                ttl_func: Optional[Callable[..., float]] = None,
                key_func: Optional[Callable[..., Any]] = None,
                cache: Optional[AsyncTTLCacheWithEviction] = None):
    """
    Caches async function results with optional per-call TTL based on result.

    Args:
        ttl: Static TTL in seconds (optional)
        ttl_func: Callable(result, *args, **kwargs) -> ttl
        key_func: Callable(*args, **kwargs) -> cache key
        cache: Optional AsyncTTLCacheWithEviction instance to use, defaults to a new instance
    """
    cache = cache or AsyncTTLCacheWithEviction()

    def decorator(fn):
        @wraps(fn)
        async def wrapper(*args, **kwargs):
            key = key_func(*args, **kwargs) if key_func else (args, frozenset(kwargs.items()))

            if await cache.has(key):
                logger.debug(f"Cache hit for {key}")
                return await cache.get(key)

            result = await fn(*args, **kwargs)

            # TTL based on result (if ttl_func given), else static ttl
            ttl_value = ttl_func(result, *args, **kwargs) if ttl_func else ttl
            await cache.set(key, result, ttl=ttl_value)

            return result
        return wrapper
    return decorator


my_cache = AsyncTTLCacheWithEviction(
    maxsize=CONFIG.CACHE_MAX_SIZE,
    cleanup_interval=CONFIG.CACHE_CLEANUP_INTERVAL
)