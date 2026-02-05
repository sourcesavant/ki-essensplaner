"""Profile API endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status

from src.api.auth import verify_token
from src.api.schemas.profile import ProfileRefreshResponse, ProfileResponse
from src.profile.preference_profile import ensure_profile_current, load_profile

router = APIRouter(prefix="/api", tags=["profile"])


@router.get("/profile", response_model=ProfileResponse)
def get_profile(_token: str = Depends(verify_token)) -> ProfileResponse:
    """Get the current preference profile.

    Returns the user's preference profile derived from meal history,
    including ingredient preferences, weekday patterns, and nutrition data.
    """
    profile = load_profile()

    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No profile found. Use POST /api/profile/refresh to generate.",
        )

    return ProfileResponse(**profile)


@router.post("/profile/refresh", response_model=ProfileRefreshResponse)
def refresh_profile(_token: str = Depends(verify_token)) -> ProfileRefreshResponse:
    """Regenerate the preference profile from meal history.

    Forces a new profile generation regardless of age.
    """
    try:
        profile, was_updated = ensure_profile_current(force=True)
        meals_analyzed = profile.get("metadata", {}).get("meals_analyzed", 0)

        return ProfileRefreshResponse(
            success=True,
            was_updated=was_updated,
            meals_analyzed=meals_analyzed,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to refresh profile: {str(e)}",
        )
