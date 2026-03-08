"""Recipe management API endpoints."""

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status

from src.api.auth import verify_token
from src.api.schemas.recipes import (
    ExcludeIngredientRequest,
    ExcludeIngredientResponse,
    ExcludedIngredientsResponse,
    RateRecipeByUrlRequest,
    RateRecipeRequest,
    RecipeRatingResponse,
)
from src.core.database import (
    exclude_ingredient,
    get_all_ratings,
    get_excluded_ingredients,
    get_recipe,
    get_recipe_by_url,
    get_recipe_book,
    get_recipe_rating,
    rate_recipe,
    remove_excluded_ingredient,
    upsert_recipe,
)
from src.models.recipe import RecipeCreate
from src.scrapers.recipe_fetcher import fetch_all_recipes

router = APIRouter(prefix="/api", tags=["recipes"])


@router.post("/recipes/{recipe_id}/rate", response_model=RecipeRatingResponse)
def rate_recipe_endpoint(
    recipe_id: int,
    request: RateRecipeRequest,
    _token: str = Depends(verify_token),
) -> RecipeRatingResponse:
    """Rate a recipe (1-5 stars).

    Sets or updates the rating for a specific recipe.
    Recipes rated with 1 star are automatically blacklisted.

    Args:
        recipe_id: The recipe database ID
        request: Rating request with rating value (1-5)

    Returns:
        RecipeRatingResponse with updated rating
    """
    # Verify recipe exists
    recipe = get_recipe(recipe_id)
    if recipe is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Recipe with ID {recipe_id} not found",
        )

    try:
        rate_recipe(recipe_id, request.rating)
        return RecipeRatingResponse(recipe_id=recipe_id, rating=request.rating)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        )


@router.post("/recipes/rate-by-url", response_model=RecipeRatingResponse)
def rate_recipe_by_url_endpoint(
    request: RateRecipeByUrlRequest,
    _token: str = Depends(verify_token),
) -> RecipeRatingResponse:
    """Rate a recipe by URL, creating a DB row first if needed."""
    recipe_url = request.recipe_url.strip()
    if not recipe_url.startswith(("http://", "https://")):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="recipe_url must start with http:// or https://",
        )

    recipe = get_recipe_by_url(recipe_url)
    if recipe is None:
        title = (request.recipe_title or "").strip() or recipe_url
        recipe = upsert_recipe(
            RecipeCreate(
                title=title,
                source="eatsmarter",
                source_url=recipe_url,
                ingredients=[],
            )
        )

    try:
        rate_recipe(recipe.id, request.rating)
        return RecipeRatingResponse(recipe_id=recipe.id, rating=request.rating)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        )


@router.get("/recipes/{recipe_id}/rating", response_model=RecipeRatingResponse)
def get_rating_endpoint(
    recipe_id: int,
    _token: str = Depends(verify_token),
) -> RecipeRatingResponse:
    """Get the rating for a recipe.

    Args:
        recipe_id: The recipe database ID

    Returns:
        RecipeRatingResponse with current rating (or None if not rated)
    """
    # Verify recipe exists
    recipe = get_recipe(recipe_id)
    if recipe is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Recipe with ID {recipe_id} not found",
        )

    rating = get_recipe_rating(recipe_id)
    return RecipeRatingResponse(recipe_id=recipe_id, rating=rating)


@router.post("/ingredients/exclude", response_model=ExcludeIngredientResponse)
def exclude_ingredient_endpoint(
    request: ExcludeIngredientRequest,
    _token: str = Depends(verify_token),
) -> ExcludeIngredientResponse:
    """Exclude an ingredient from all future recipes.

    Adds the ingredient to the exclusion list. Future recipe searches
    will filter out recipes containing this ingredient.

    Args:
        request: Ingredient exclusion request

    Returns:
        ExcludeIngredientResponse with confirmation
    """
    ingredient_name = request.ingredient_name.strip().lower()

    if not ingredient_name:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Ingredient name cannot be empty",
        )

    try:
        exclude_ingredient(ingredient_name)
        return ExcludeIngredientResponse(
            message=f"Ingredient '{ingredient_name}' has been excluded",
            ingredient_name=ingredient_name,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to exclude ingredient: {str(e)}",
        )


@router.delete("/ingredients/exclude/{ingredient_name}", status_code=status.HTTP_204_NO_CONTENT)
def remove_exclusion_endpoint(
    ingredient_name: str,
    _token: str = Depends(verify_token),
) -> None:
    """Remove an ingredient from the exclusion list.

    Args:
        ingredient_name: The ingredient to remove from exclusions
    """
    ingredient_name = ingredient_name.strip().lower()

    if not ingredient_name:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Ingredient name cannot be empty",
        )

    success = remove_excluded_ingredient(ingredient_name)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Ingredient '{ingredient_name}' is not in the exclusion list",
        )


@router.get("/ingredients/excluded", response_model=ExcludedIngredientsResponse)
def get_excluded_ingredients_endpoint(
    _token: str = Depends(verify_token),
) -> ExcludedIngredientsResponse:
    """Get all excluded ingredients.

    Returns the complete list of ingredients that are currently excluded
    from recipe searches.

    Returns:
        ExcludedIngredientsResponse with list of excluded ingredients
    """
    excluded = get_excluded_ingredients()
    return ExcludedIngredientsResponse(ingredients=sorted(excluded))


@router.get("/recipes/ratings")
def get_all_ratings_endpoint(
    _token: str = Depends(verify_token),
) -> dict:
    """Gibt alle Bewertungen als {recipe_id: rating} zurück."""
    return get_all_ratings()


@router.get("/recipes/book")
def get_recipe_book_endpoint(
    _token: str = Depends(verify_token),
) -> dict:
    """Rezeptbuch: alle gekochten/bewerteten Rezepte mit Statistiken."""
    return {"recipes": get_recipe_book()}


@router.post("/recipes/fetch")
def fetch_recipes_endpoint(
    background_tasks: BackgroundTasks,
    delay_seconds: float = 0.5,
    _token: str = Depends(verify_token),
) -> dict:
    """Trigger background recipe fetching from meal URLs.

    Args:
        delay_seconds: Delay between requests to avoid rate limiting
    """
    background_tasks.add_task(fetch_all_recipes, delay_seconds)
    return {"status": "started", "delay_seconds": delay_seconds}
