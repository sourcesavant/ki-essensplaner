"""Fetch and scrape recipes from URLs stored in meal plans.

This module extracts recipe URLs from the meals table (imported from OneNote)
and scrapes the full recipe data (title, ingredients, instructions, nutrition)
from the source websites.

Supported scrapers:
- recipe-scrapers library: eatsmarter.de, jamieoliver.com, emmikochteinfach.de, etc.
- Custom scrapers: familienkost.de (uses JSON-LD structured data)

The scraping process:
1. Extract unique URLs from meals.recipe_title (where recipe_id is NULL)
2. For each URL, use the appropriate scraper to fetch recipe data
3. Store recipe in database and link to meals via recipe_id
4. Rate limiting (0.5s delay) to avoid being blocked

Example usage:
    >>> from src.scrapers.recipe_fetcher import fetch_all_recipes
    >>> stats = fetch_all_recipes(delay_seconds=0.5)
    >>> print(f"Scraped: {stats['scraped']}, Failed: {stats['failed']}")

Issue #3: Rufe Rezepte von gespeicherten Links ab
Issue #7: Extrahiere Nährwertdaten aus Rezeptseiten
"""

import re
import time
from urllib.parse import urlparse

from recipe_scrapers import scrape_me
from recipe_scrapers._exceptions import WebsiteNotImplementedError

from src.core.database import get_connection, get_recipe_by_url, upsert_recipe
from src.models.recipe import RecipeCreate
from src.scrapers.familienkost import scrape_familienkost

# Registry of custom scrapers for sites not supported by recipe-scrapers
# Key: domain (without www.), Value: scraper function
CUSTOM_SCRAPERS = {
    "familienkost.de": scrape_familienkost,
}


def get_meal_urls() -> list[dict]:
    """Extract all unique URLs from meals.recipe_title.

    Returns:
        List of dicts with 'url' and 'meal_ids' (list of meal IDs using this URL)
    """
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, recipe_title
            FROM meals
            WHERE recipe_title LIKE 'http%'
            AND recipe_id IS NULL
            ORDER BY recipe_title
            """
        ).fetchall()

    # Group by URL to get all meal IDs per URL
    url_map: dict[str, list[int]] = {}
    for row in rows:
        url = row["recipe_title"].strip()
        meal_id = row["id"]
        if url not in url_map:
            url_map[url] = []
        url_map[url].append(meal_id)

    return [{"url": url, "meal_ids": ids} for url, ids in url_map.items()]


def parse_nutrition_value(value: str | None) -> float | None:
    """Parse nutrition value string to float.

    Examples:
        '293 kcal' -> 293
        '22 g' -> 22.0
        '3.7 g' -> 3.7
    """
    if not value:
        return None
    # Extract first number (int or float)
    match = re.search(r"(\d+(?:[.,]\d+)?)", value)
    if match:
        num_str = match.group(1).replace(",", ".")
        return float(num_str)
    return None


def parse_servings(yields_str: str | None) -> int | None:
    """Parse servings from yields string.

    Examples:
        '4 Portionen' -> 4
        '4' -> 4
        'für 4 Personen' -> 4
        'Serves 4' -> 4
        '2-4 Portionen' -> 4 (take the maximum)

    Args:
        yields_str: Raw yields string from recipe

    Returns:
        Number of servings or None if parsing failed
    """
    if not yields_str:
        return None

    # Pattern for single number: "4 Portionen", "4", "für 4 Personen", "Serves 4"
    match = re.search(r'(\d+)', yields_str)
    if match:
        return int(match.group(1))

    return None


def extract_source_from_url(url: str) -> str:
    """Extract source name from URL domain.

    Examples:
        https://eatsmarter.de/... -> 'eatsmarter'
        https://www.kochkarussell.com/... -> 'kochkarussell'
    """
    parsed = urlparse(url)
    domain = parsed.netloc.lower()
    # Remove www. prefix
    if domain.startswith("www."):
        domain = domain[4:]
    # Take first part before .de/.com/etc
    source = domain.split(".")[0]
    return source


def scrape_recipe(url: str) -> RecipeCreate | None:
    """Scrape a recipe from URL using recipe-scrapers or custom scrapers.

    Args:
        url: The recipe URL to scrape

    Returns:
        RecipeCreate model or None if scraping failed
    """
    # Check for custom scrapers first
    parsed = urlparse(url)
    domain = parsed.netloc.lower()
    if domain.startswith("www."):
        domain = domain[4:]

    if domain in CUSTOM_SCRAPERS:
        return CUSTOM_SCRAPERS[domain](url)

    # Fall back to recipe-scrapers
    try:
        scraper = scrape_me(url)

        # Get total time, handle None
        total_time = None
        try:
            total_time = scraper.total_time()
        except Exception:
            pass

        # Get ingredients
        ingredients = []
        try:
            ingredients = scraper.ingredients()
        except Exception:
            pass

        # Get instructions
        instructions = None
        try:
            instructions = scraper.instructions()
        except Exception:
            pass

        # Get nutrition info
        calories = None
        fat_g = None
        protein_g = None
        carbs_g = None
        try:
            nutrients = scraper.nutrients()
            if nutrients:
                calories_val = parse_nutrition_value(nutrients.get("calories"))
                calories = int(calories_val) if calories_val else None
                fat_g = parse_nutrition_value(nutrients.get("fatContent"))
                protein_g = parse_nutrition_value(nutrients.get("proteinContent"))
                carbs_g = parse_nutrition_value(nutrients.get("carbohydrateContent"))
        except Exception:
            pass

        # Get servings
        servings = None
        try:
            yields_str = scraper.yields()
            servings = parse_servings(yields_str)
        except Exception:
            pass

        return RecipeCreate(
            title=scraper.title(),
            source=extract_source_from_url(url),
            source_url=url,
            prep_time_minutes=total_time,
            ingredients=ingredients,
            instructions=instructions,
            calories=calories,
            fat_g=fat_g,
            protein_g=protein_g,
            carbs_g=carbs_g,
            servings=servings,
        )

    except WebsiteNotImplementedError:
        print(f"  [!] Site not supported: {url}")
        return None
    except Exception as e:
        print(f"  [X] Error scraping {url}: {e}")
        return None


def link_meals_to_recipe(meal_ids: list[int], recipe_id: int) -> None:
    """Update meals to link to a recipe.

    Args:
        meal_ids: List of meal IDs to update
        recipe_id: The recipe ID to link to
    """
    with get_connection() as conn:
        conn.executemany(
            "UPDATE meals SET recipe_id = ? WHERE id = ?",
            [(recipe_id, meal_id) for meal_id in meal_ids]
        )


def fetch_all_recipes(
    delay_seconds: float = 0.5,
    skip_existing: bool = True,
    limit: int | None = None,
) -> dict:
    """Fetch all recipes from URLs in meal plans.

    Args:
        delay_seconds: Delay between requests to avoid rate limiting
        skip_existing: Skip URLs already in recipes table
        limit: Maximum number of URLs to process (None = all)

    Returns:
        Dict with stats: {scraped, skipped, failed, linked_meals}
    """
    import os
    from src.core.config import DB_PATH
    print(f"[RecipeFetch] Using DB: {DB_PATH} (DATA_DIR={os.getenv('DATA_DIR')})")
    stats = {"scraped": 0, "skipped": 0, "failed": 0, "linked_meals": 0}

    url_data = get_meal_urls()
    if limit:
        url_data = url_data[:limit]

    print(f"Found {len(url_data)} unique URLs to process")
    print("=" * 50)

    for i, item in enumerate(url_data, 1):
        url = item["url"]
        meal_ids = item["meal_ids"]

        print(f"[{i}/{len(url_data)}] {url[:60]}...")

        # Check if already exists
        if skip_existing:
            existing = get_recipe_by_url(url)
            if existing:
                print(f"  [OK] Already in DB (ID: {existing.id}), linking {len(meal_ids)} meals")
                link_meals_to_recipe(meal_ids, existing.id)
                stats["skipped"] += 1
                stats["linked_meals"] += len(meal_ids)
                continue

        # Scrape the recipe
        recipe_data = scrape_recipe(url)

        if recipe_data:
            recipe = upsert_recipe(recipe_data)
            print(f"  [OK] Scraped: {recipe.title} (ID: {recipe.id})")
            link_meals_to_recipe(meal_ids, recipe.id)
            stats["scraped"] += 1
            stats["linked_meals"] += len(meal_ids)
        else:
            stats["failed"] += 1

        # Rate limiting
        if i < len(url_data):
            time.sleep(delay_seconds)

    print("=" * 50)
    print(f"Done! Scraped: {stats['scraped']}, Skipped: {stats['skipped']}, "
          f"Failed: {stats['failed']}, Linked meals: {stats['linked_meals']}")

    return stats


def get_scraping_stats() -> dict:
    """Get current scraping statistics.

    Returns:
        Dict with counts of URLs, recipes, linked/unlinked meals
    """
    with get_connection() as conn:
        # Total URLs in meals
        url_count = conn.execute(
            "SELECT COUNT(DISTINCT recipe_title) FROM meals WHERE recipe_title LIKE 'http%'"
        ).fetchone()[0]

        # Linked meals (have recipe_id)
        linked_count = conn.execute(
            "SELECT COUNT(*) FROM meals WHERE recipe_id IS NOT NULL"
        ).fetchone()[0]

        # Unlinked URL meals
        unlinked_url_count = conn.execute(
            "SELECT COUNT(*) FROM meals WHERE recipe_title LIKE 'http%' AND recipe_id IS NULL"
        ).fetchone()[0]

        # Total recipes
        recipe_count = conn.execute("SELECT COUNT(*) FROM recipes").fetchone()[0]

        # Recipes by source
        sources = conn.execute(
            "SELECT source, COUNT(*) as count FROM recipes GROUP BY source ORDER BY count DESC"
        ).fetchall()

    return {
        "unique_urls": url_count,
        "recipes_in_db": recipe_count,
        "linked_meals": linked_count,
        "unlinked_url_meals": unlinked_url_count,
        "recipes_by_source": {row["source"]: row["count"] for row in sources},
    }


if __name__ == "__main__":
    # Show current stats
    print("Current stats:")
    stats = get_scraping_stats()
    print(f"  Unique URLs: {stats['unique_urls']}")
    print(f"  Recipes in DB: {stats['recipes_in_db']}")
    print(f"  Linked meals: {stats['linked_meals']}")
    print(f"  Unlinked URL meals: {stats['unlinked_url_meals']}")
    print()

    # Fetch all recipes
    fetch_all_recipes(delay_seconds=0.5)
