"""Pydantic schemas for onboarding endpoints."""

from pydantic import BaseModel, Field


class OneNoteAuthStatusResponse(BaseModel):
    """OneNote authentication status."""

    authenticated: bool
    user_email: str | None = None
    notebooks_available: int = 0


class NotebookInfo(BaseModel):
    """Information about a OneNote notebook."""

    id: str
    name: str
    created_at: str | None = None


class NotebooksResponse(BaseModel):
    """List of available notebooks."""

    notebooks: list[NotebookInfo] = Field(default_factory=list)
    total: int = 0


class ImportRequest(BaseModel):
    """Request to import data from OneNote notebooks."""

    notebook_ids: list[str] = Field(..., min_length=1, description="List of notebook IDs to import")
    notebook_filter: list[str] | None = Field(None, description="Optional notebook name filters")


class ImportResponse(BaseModel):
    """Response from import operation."""

    message: str
    status: str  # "started", "completed"
    pages_found: int = 0
    recipes_imported: int = 0


class ProfileGenerateResponse(BaseModel):
    """Response from profile generation."""

    message: str
    status: str  # "started", "completed"
    meals_analyzed: int = 0
    profile_created: bool = False


class OnboardingStatusResponse(BaseModel):
    """Overall onboarding status."""

    azure_configured: bool
    onenote_authenticated: bool
    data_imported: bool
    profile_generated: bool
    ready_for_use: bool
    next_step: str | None = None
