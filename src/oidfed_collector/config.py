# ==============================================================
#       |
#   \  ___  /                           _________
#  _  /   \  _    GÉANT                 |  * *  | Co-Funded by
#     | ~ |       Trust & Identity      | *   * | the European
#      \_/        Incubator             |__*_*__| Union
#       =
# ==============================================================

import os
from pathlib import Path
import json
from pydantic import BaseModel, Field


class CacheConfig(BaseModel):
    ttl: int = Field(300, description="Default cache TTL in seconds")
    max_size: int = Field(1000, description="Maximum cache size in items")
    cleanup_interval: int = Field(60, description="Cache cleanup interval in seconds")


class SessionConfig(BaseModel):
    max_concurrent_requests: int = Field(100, description="Maximum concurrent requests allowed in a session")
    ttl: int = Field(300, description="Session TTL in seconds")


class AppConfig(BaseModel):
    port: int = Field(12345, description="Port on which the app runs")
    log_level: str = Field("info", description="Logging level for the application")
    api_base_url: str = Field("/collection", description="Base URL for the API")
    cache: CacheConfig = Field(..., description="Configuration for the cache system",)
    session: SessionConfig = Field(..., description="Configuration for the session management")


def load_config(path: str | Path) -> AppConfig:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    with path.open("r", encoding="utf-8") as f:
        raw = json.load(f)
    return AppConfig(**raw)


CONFIG = load_config(os.getenv("CONFIG", "config.json"))
