"""Entry point for running the API server.

Usage:
    python -m src.api
"""

import uvicorn

from src.api.config import config


def main() -> None:
    """Run the API server."""
    uvicorn.run(
        "src.api.main:app",
        host=config.host,
        port=config.port,
        reload=config.debug,
    )


if __name__ == "__main__":
    main()
