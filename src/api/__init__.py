"""KI-Essensplaner REST API package.

This package provides a FastAPI-based REST API for the KI-Essensplaner,
enabling integration with Home Assistant and other clients.

Usage:
    python -m src.api
"""

from src.api.main import app

__all__ = ["app"]
