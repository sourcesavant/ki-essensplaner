"""Health check endpoint."""

from fastapi import APIRouter

from src.api.schemas.common import HealthResponse
from src.core.database import get_connection
from src.profile.preference_profile import get_profile_age
from src.scrapers.bioland_huesgen import get_bioland_data_age

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health_check() -> HealthResponse:
    """Check API and data health status.

    Returns health information including:
    - Database connectivity
    - Profile data age
    - Bioland data age
    - Whether data is from cache
    """
    # Check database connectivity
    database_ok = False
    try:
        with get_connection() as conn:
            conn.execute("SELECT 1")
            database_ok = True
    except Exception:
        pass

    # Get profile age
    profile_age_days: int | None = None
    profile_age = get_profile_age()
    if profile_age is not None:
        profile_age_days = profile_age.days

    # Get bioland data age
    bioland_age_days: int | None = None
    bioland_age = get_bioland_data_age()
    if bioland_age is not None:
        bioland_age_days = bioland_age.days

    # Determine overall status
    if not database_ok:
        status = "offline"
    elif profile_age_days is not None and profile_age_days > 7:
        status = "cached"
    elif bioland_age_days is not None and bioland_age_days > 7:
        status = "cached"
    else:
        status = "healthy"

    return HealthResponse(
        status=status,
        database_ok=database_ok,
        profile_age_days=profile_age_days,
        bioland_age_days=bioland_age_days,
        cached=status == "cached",
    )
