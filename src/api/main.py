"""FastAPI application setup."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.config import config
from src.core.database import init_db, migrate_db_if_needed


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize database on startup."""
    migrate_db_if_needed()
    init_db()
    yield
from src.api.routers.bioland import router as bioland_router
from src.api.routers.config import router as config_router
from src.api.routers.health import router as health_router
from src.api.routers.onboarding import router as onboarding_router
from src.api.routers.profile import router as profile_router
from src.api.routers.recipes import router as recipes_router
from src.api.routers.seasonality import router as seasonality_router
from src.api.routers.shopping import router as shopping_router
from src.api.routers.weekly_plan import router as weekly_plan_router

# Create FastAPI app
app = FastAPI(
    title="KI-Essensplaner API",
    description="REST API für den KI-Essensplaner - personalisierte Wochenpläne",
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)

# Configure CORS
if config.cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
else:
    # Allow all origins in development
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

# Include routers
app.include_router(health_router)
app.include_router(profile_router)
app.include_router(config_router)
app.include_router(bioland_router)
app.include_router(seasonality_router)
app.include_router(weekly_plan_router)
app.include_router(shopping_router)
app.include_router(recipes_router)
app.include_router(onboarding_router)
