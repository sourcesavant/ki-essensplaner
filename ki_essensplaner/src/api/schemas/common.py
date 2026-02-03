"""Common API schemas used across endpoints."""

from pydantic import BaseModel


class HealthResponse(BaseModel):
    """Response schema for health check endpoint."""

    status: str
    database_ok: bool
    profile_age_days: int | None = None
    bioland_age_days: int | None = None
    cached: bool = False


class ErrorResponse(BaseModel):
    """Standard error response schema."""

    error: str
    detail: str | None = None
