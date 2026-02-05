"""API routers package."""

from src.api.routers.bioland import router as bioland_router
from src.api.routers.health import router as health_router
from src.api.routers.profile import router as profile_router
from src.api.routers.seasonality import router as seasonality_router

__all__ = ["health_router", "profile_router", "bioland_router", "seasonality_router"]
