
class Config:
    """Configuration for OIDC-FED Collection."""
    
    # General settings
    API_PREFIX = "/collection"
    
    # Cache settings
    CACHE_TTL = 3600  # Default cache TTL in seconds
    CACHE_MAX_SIZE = 10000  # Maximum size of the cache
    CACHE_CLEANUP_INTERVAL = 300  # Cleanup interval in seconds
    
    # HTTP session settings
    SESSION_MAX_CONCURRENT_REQUESTS = 1000  # Adjust based on your server's capacity
    SESSION_TTL = 600


CONFIG = Config()