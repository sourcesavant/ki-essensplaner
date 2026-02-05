"""API configuration management.

Loads configuration from environment variables with sensible defaults.
"""

import os
from dataclasses import dataclass


@dataclass
class APIConfig:
    """API server configuration."""

    host: str = "0.0.0.0"
    port: int = 8099
    api_token: str | None = None
    debug: bool = False
    cors_origins: list[str] | None = None
    log_level: str = "info"

    @classmethod
    def from_env(cls) -> "APIConfig":
        """Load configuration from environment variables."""
        cors_origins_str = os.getenv("API_CORS_ORIGINS", "")
        cors_origins = [o.strip() for o in cors_origins_str.split(",") if o.strip()] or None

        return cls(
            host=os.getenv("API_HOST", "0.0.0.0"),
            port=int(os.getenv("API_PORT", "8099")),
            api_token=os.getenv("API_TOKEN"),
            debug=os.getenv("API_DEBUG", "").lower() in ("true", "1", "yes"),
            cors_origins=cors_origins,
            log_level=os.getenv("API_LOG_LEVEL", os.getenv("LOG_LEVEL", "info")).lower(),
        )


# Global config instance
config = APIConfig.from_env()
