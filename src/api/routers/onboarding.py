"""Onboarding API endpoints for initial setup."""

import asyncio
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status

from src.api.auth import verify_token
from src.api.schemas.onboarding import (
    AuthCompleteResponse,
    DeviceCodeResponse,
    ImportRequest,
    ImportResponse,
    NotebookInfo,
    NotebooksResponse,
    OnboardingStatusResponse,
    OneNoteAuthStatusResponse,
    ProfileGenerateResponse,
)
from src.core.config import AzureConfig, LOCAL_DIR
from src.core.database import get_connection
from src.importers.onenote import OneNoteClient
from src.profile.preference_profile import (
    PROFILE_PATH,
    ensure_profile_current,
    generate_profile,
)

router = APIRouter(prefix="/api/onboarding", tags=["onboarding"])


def _check_azure_configured() -> bool:
    """Check if Azure credentials are configured."""
    return AzureConfig.is_configured()


def _check_onenote_authenticated() -> tuple[bool, str | None]:
    """Check if OneNote is authenticated.

    Returns:
        Tuple of (authenticated, user_email)
    """
    import logging
    logger = logging.getLogger(__name__)

    try:
        logger.info("Checking OneNote authentication...")
        client = OneNoteClient()
        if not client.try_authenticate_from_cache():
            logger.info("No cached OneNote token available.")
            return False, None
        logger.info("OneNoteClient created, attempting to get notebooks...")
        # Try to get notebooks - if this works, we're authenticated
        notebooks = client.get_notebooks()
        logger.info(f"Successfully retrieved {len(notebooks)} notebooks")
        return True, None  # We don't get email from Graph API easily
    except Exception as e:
        logger.error(f"OneNote authentication check failed: {e}", exc_info=True)
        return False, None


def _check_data_imported() -> bool:
    """Check if any meal data has been imported."""
    with get_connection() as conn:
        count = conn.execute("SELECT COUNT(*) FROM meals").fetchone()[0]
        return count > 0


def _check_profile_generated() -> bool:
    """Check if a profile has been generated."""
    return PROFILE_PATH.exists()


def _import_from_notebooks_sync(notebook_ids: list[str], notebook_filter: list[str] | None = None) -> dict:
    """Synchronous import from OneNote notebooks.

    Args:
        notebook_ids: List of notebook IDs to import
        notebook_filter: Optional list of notebook name filters

    Returns:
        Dict with import statistics
    """
    try:
        client = OneNoteClient()
        if not client.try_authenticate_from_cache():
            return {"pages_found": 0, "recipes_imported": 0, "error": "OneNote not authenticated"}

        # Get all notebooks
        all_notebooks = client.get_notebooks()

        # Filter by IDs or names
        notebooks_to_import = []
        for notebook in all_notebooks:
            if notebook["id"] in notebook_ids:
                notebooks_to_import.append(notebook)
            elif notebook_filter:
                if any(f.lower() in notebook["displayName"].lower() for f in notebook_filter):
                    notebooks_to_import.append(notebook)

        if not notebooks_to_import:
            return {"pages_found": 0, "recipes_imported": 0, "error": "No matching notebooks found"}

        # Import from each notebook
        from src.importers.onenote import import_meal_plans_cached

        notebook_names = [nb["displayName"] for nb in notebooks_to_import]
        import_result = import_meal_plans_cached(
            client,
            notebooks_filter=notebook_names,
            export_raw=True,
        )

        # Get recipe and meal counts
        with get_connection() as conn:
            recipe_count = conn.execute("SELECT COUNT(*) FROM recipes").fetchone()[0]
            meal_count = conn.execute("SELECT COUNT(*) FROM meals").fetchone()[0]
            plan_count = conn.execute("SELECT COUNT(*) FROM meal_plans").fetchone()[0]

        return {
            "pages_found": import_result.get("pages_found", 0),
            "recipes_imported": recipe_count,
            "meals_imported": meal_count,
            "meal_plans_imported": plan_count,
        }

    except Exception as e:
        return {"pages_found": 0, "recipes_imported": 0, "error": str(e)}


def _generate_profile_sync() -> dict:
    """Synchronous profile generation.

    Returns:
        Dict with profile statistics
    """
    try:
        profile, was_updated = ensure_profile_current(force=True)

        if profile:
            meals_analyzed = profile.get("metadata", {}).get("meals_analyzed", 0)
            return {
                "meals_analyzed": meals_analyzed,
                "profile_created": True,
            }
        else:
            return {
                "meals_analyzed": 0,
                "profile_created": False,
                "error": "Failed to generate profile",
            }

    except Exception as e:
        return {
            "meals_analyzed": 0,
            "profile_created": False,
            "error": str(e),
        }


@router.get("/status", response_model=OnboardingStatusResponse)
def get_onboarding_status(_token: str = Depends(verify_token)) -> OnboardingStatusResponse:
    """Get overall onboarding status.

    Returns the current state of onboarding progress:
    - Azure configuration
    - OneNote authentication
    - Data import status
    - Profile generation status

    Also provides guidance on the next step.
    """
    azure_configured = _check_azure_configured()
    onenote_authenticated, _ = _check_onenote_authenticated() if azure_configured else (False, None)
    data_imported = _check_data_imported()
    profile_generated = _check_profile_generated()

    ready_for_use = all([azure_configured, onenote_authenticated, data_imported, profile_generated])

    # Determine next step
    next_step = None
    if not azure_configured:
        next_step = "Configure Azure credentials (azure_client_id in addon configuration)"
    elif not onenote_authenticated:
        next_step = "Authenticate with OneNote (POST /api/onboarding/onenote/auth/start)"
    elif not data_imported:
        next_step = "Import data from OneNote notebooks (POST /api/onboarding/import)"
    elif not profile_generated:
        next_step = "Generate preference profile (POST /api/onboarding/profile/generate)"
    else:
        next_step = "Ready! You can now generate weekly plans."

    return OnboardingStatusResponse(
        azure_configured=azure_configured,
        onenote_authenticated=onenote_authenticated,
        data_imported=data_imported,
        profile_generated=profile_generated,
        ready_for_use=ready_for_use,
        next_step=next_step,
    )


@router.post("/onenote/auth/start", response_model=DeviceCodeResponse)
def start_onenote_auth(_token: str = Depends(verify_token)) -> DeviceCodeResponse:
    """Start OneNote authentication using device code flow.

    Returns a user code and URL. The user should:
    1. Go to the verification URL
    2. Enter the user code
    3. Sign in with their Microsoft account
    4. Call /api/onboarding/onenote/auth/complete to finish

    The code expires after ~15 minutes.
    """
    if not _check_azure_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Azure credentials not configured. Set azure_client_id in addon configuration.",
        )

    try:
        client = OneNoteClient()

        # Check if already authenticated AND token is valid
        if client.try_authenticate_from_cache():
            # Verify the token works by trying to get notebooks
            try:
                client.get_notebooks()
                # Token works, already authenticated
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Already authenticated with OneNote. No need to re-authenticate.",
                )
            except Exception:
                # Token doesn't work, continue with new auth
                pass

        # Start device flow
        flow_data = client.start_device_flow()
        if not flow_data:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to start authentication flow.",
            )

        return DeviceCodeResponse(
            user_code=flow_data["user_code"],
            verification_uri=flow_data["verification_uri"],
            message=flow_data["message"],
            expires_in=flow_data["expires_in"],
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to start authentication: {str(e)}",
        )


@router.post("/onenote/auth/complete", response_model=AuthCompleteResponse)
def complete_onenote_auth(
    background_tasks: BackgroundTasks,
    _token: str = Depends(verify_token),
) -> AuthCompleteResponse:
    """Complete OneNote authentication after user has entered the code.

    This endpoint will wait (up to 5 minutes) for the user to complete
    authentication at the Microsoft login page.

    After successful authentication, the user can select notebooks to import
    via the notebook selection step in the config flow.

    Call this AFTER the user has entered the code at the verification URL.
    """
    if not _check_azure_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Azure credentials not configured.",
        )

    try:
        client = OneNoteClient()

        # Complete the device flow (this blocks until user authenticates)
        success = client.complete_device_flow(timeout=300)

        if success:
            # Get notebooks count
            notebooks = client.get_notebooks()
            notebook_count = len(notebooks)

            return AuthCompleteResponse(
                authenticated=True,
                message=f"Successfully authenticated! {notebook_count} notebooks available for import.",
                notebooks_available=notebook_count,
            )
        else:
            return AuthCompleteResponse(
                authenticated=False,
                message="Authentication failed or timed out. Please try again.",
                notebooks_available=0,
            )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Authentication failed: {str(e)}",
        )


def _auto_import_and_generate_profile(notebook_ids: list[str]) -> None:
    """Background task to import notebooks and generate profile."""
    import logging
    logger = logging.getLogger(__name__)

    try:
        logger.info(f"Starting auto-import of {len(notebook_ids)} notebooks...")

        # Import from notebooks
        result = _import_from_notebooks_sync(notebook_ids, None)
        logger.info(f"Import complete: {result}")

        # Generate profile
        if _check_data_imported():
            logger.info("Generating preference profile...")
            profile_result = _generate_profile_sync()
            logger.info(f"Profile generation complete: {profile_result}")
        else:
            logger.warning("No data imported, skipping profile generation")

    except Exception as e:
        logger.error(f"Auto-import failed: {e}")


@router.get("/onenote/auth/status", response_model=OneNoteAuthStatusResponse)
def get_onenote_auth_status(_token: str = Depends(verify_token)) -> OneNoteAuthStatusResponse:
    """Check OneNote authentication status.

    Returns whether OneNote is authenticated and ready to use.
    If not authenticated, use the Home Assistant integration setup flow to authenticate.
    """
    if not _check_azure_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Azure credentials not configured. Set AZURE_CLIENT_ID and AZURE_TENANT_ID in .env file.",
        )

    authenticated, user_email = _check_onenote_authenticated()

    notebooks_count = 0
    if authenticated:
        try:
            client = OneNoteClient()
            notebooks = client.get_notebooks()
            notebooks_count = len(notebooks)
        except Exception:
            pass

    return OneNoteAuthStatusResponse(
        authenticated=authenticated,
        user_email=user_email,
        notebooks_available=notebooks_count,
    )


@router.get("/onenote/notebooks", response_model=NotebooksResponse)
def get_notebooks(_token: str = Depends(verify_token)) -> NotebooksResponse:
    """Get list of available OneNote notebooks.

    Requires OneNote authentication.
    Returns list of notebooks that can be selected for import.
    """
    if not _check_azure_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Azure credentials not configured.",
        )

    authenticated, _ = _check_onenote_authenticated()
    if not authenticated:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="OneNote not authenticated. Please authenticate via Home Assistant integration setup or POST /api/onboarding/onenote/auth/start",
        )

    try:
        client = OneNoteClient()
        if not client.try_authenticate_from_cache():
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="OneNote not authenticated. Please authenticate via Home Assistant integration setup or POST /api/onboarding/onenote/auth/start",
            )
        notebooks = client.get_notebooks()

        notebook_list = [
            NotebookInfo(
                id=nb["id"],
                name=nb["displayName"],
                created_at=nb.get("createdDateTime"),
            )
            for nb in notebooks
        ]

        return NotebooksResponse(
            notebooks=notebook_list,
            total=len(notebook_list),
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch notebooks: {str(e)}",
        )


@router.post("/import", response_model=ImportResponse)
def import_data(
    request: ImportRequest,
    background_tasks: BackgroundTasks,
    _token: str = Depends(verify_token),
) -> ImportResponse:
    """Import meal data from selected OneNote notebooks.

    This operation runs in the background as it may take 30-60 seconds.
    The import process:
    1. Fetches pages from selected notebooks
    2. Parses meal plans from page content
    3. Imports recipes and meals into database

    Returns immediately with a started status.
    """
    if not _check_azure_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Azure credentials not configured.",
        )

    authenticated, _ = _check_onenote_authenticated()
    if not authenticated:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="OneNote not authenticated.",
        )

    import logging
    logger = logging.getLogger("uvicorn.error")
    msg = f"Import requested: notebook_ids={request.notebook_ids} notebook_filter={request.notebook_filter}"
    logger.info(msg)
    print(msg, flush=True)

    # For simplicity, run synchronously (small dataset)
    # In production, use background_tasks.add_task()
    result = _import_from_notebooks_sync(request.notebook_ids, request.notebook_filter)

    if "error" in result:
        msg = f"Import failed: {result['error']}"
        logger.error(msg)
        print(msg, flush=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=result["error"],
        )

    msg = f"Import completed: {result}"
    logger.info(msg)
    print(msg, flush=True)
    return ImportResponse(
        message="Import completed successfully",
        status="completed",
        pages_found=result["pages_found"],
        recipes_imported=result["recipes_imported"],
    )


@router.post("/profile/generate", response_model=ProfileGenerateResponse)
def generate_profile_endpoint(
    background_tasks: BackgroundTasks,
    _token: str = Depends(verify_token),
) -> ProfileGenerateResponse:
    """Generate initial preference profile from imported data.

    Analyzes meal history to derive:
    - Ingredient preferences
    - Effort patterns per weekday
    - Nutrition patterns

    Requires at least some meals to be imported first.
    """
    if not _check_data_imported():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No meal data found. Import data from OneNote first using POST /api/onboarding/import.",
        )

    # For simplicity, run synchronously
    result = _generate_profile_sync()

    if "error" in result:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=result["error"],
        )

    return ProfileGenerateResponse(
        message="Profile generated successfully",
        status="completed",
        meals_analyzed=result["meals_analyzed"],
        profile_created=result["profile_created"],
    )
