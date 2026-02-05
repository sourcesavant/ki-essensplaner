"""Playwright-based scraper for eatsmarter.de recipe search.

Uses the eatsmarter.de search page with query parameters for ingredient-based
recipe search. Playwright is needed to handle dynamic content loading.

Example usage:
    >>> from src.scrapers.eatsmarter_search import search_recipes
    >>> results = search_recipes(
    ...     include_ingredients=["tomate", "mozzarella"],
    ...     meal_type="Abendessen",
    ...     max_time=30
    ... )
    >>> for r in results:
    ...     print(f"{r.title} ({r.prep_time_minutes} min)")
"""

import hashlib
import json
import re
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from urllib.parse import quote_plus

from src.core.config import LOCAL_DIR, ensure_directories

# Cache configuration
CACHE_FILE = LOCAL_DIR / "search_cache.json"
CACHE_TTL_DAYS = 7

# eatsmarter.de configuration
BASE_URL = "https://eatsmarter.de"
SEARCH_URL = f"{BASE_URL}/suche/rezepte"

# Meal type keywords for filtering results
MEAL_TYPE_KEYWORDS = {
    "Mittagessen": ["mittag", "lunch", "hauptgericht", "hauptspeise"],
    "Abendessen": ["abend", "dinner", "hauptgericht", "hauptspeise"],
    "Frühstück": ["frühstück", "breakfast", "morgen"],
    "Snacks": ["snack", "zwischenmahlzeit", "happen"],
}


@dataclass
class SearchResult:
    """A recipe search result from eatsmarter.de."""

    title: str
    url: str
    prep_time_minutes: int | None = None
    total_time_minutes: int | None = None
    calories: int | None = None
    image_url: str | None = None
    rating: float | None = None
    health_score: int | None = None

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "SearchResult":
        """Create from dictionary."""
        return cls(**data)


def _get_cache_key(
    include_ingredients: list[str],
    meal_type: str | None,
    max_time: int | None,
) -> str:
    """Generate a unique cache key for search parameters."""
    params = {
        "ingredients": sorted([i.lower().strip() for i in include_ingredients]),
        "meal_type": meal_type,
        "max_time": max_time,
    }
    param_str = json.dumps(params, sort_keys=True)
    return hashlib.md5(param_str.encode()).hexdigest()


def _load_cache() -> dict:
    """Load the search cache from disk."""
    if not CACHE_FILE.exists():
        return {}
    try:
        with open(CACHE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _save_cache(cache: dict) -> None:
    """Save the search cache to disk."""
    ensure_directories()
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


def _is_cache_valid(cache_entry: dict) -> bool:
    """Check if a cache entry is still valid (within TTL)."""
    if "cached_at" not in cache_entry:
        return False
    cached_at = datetime.fromisoformat(cache_entry["cached_at"])
    return datetime.now() - cached_at < timedelta(days=CACHE_TTL_DAYS)


def _get_cached_results(cache_key: str) -> list[SearchResult] | None:
    """Get cached results if available and valid."""
    cache = _load_cache()
    if cache_key in cache and _is_cache_valid(cache[cache_key]):
        results_data = cache[cache_key].get("results", [])
        return [SearchResult.from_dict(r) for r in results_data]
    return None


def _cache_results(cache_key: str, results: list[SearchResult]) -> None:
    """Cache search results."""
    cache = _load_cache()
    cache[cache_key] = {
        "cached_at": datetime.now().isoformat(),
        "results": [r.to_dict() for r in results],
    }
    _save_cache(cache)


def _parse_time(time_str: str | None) -> int | None:
    """Parse time string like '30 Min.' or '1 Std. 20 Min.' to minutes."""
    if not time_str:
        return None

    total_minutes = 0

    # Match hours
    hours_match = re.search(r"(\d+)\s*Std", time_str)
    if hours_match:
        total_minutes += int(hours_match.group(1)) * 60

    # Match minutes
    minutes_match = re.search(r"(\d+)\s*Min", time_str)
    if minutes_match:
        total_minutes += int(minutes_match.group(1))

    return total_minutes if total_minutes > 0 else None


def _parse_calories(cal_str: str | None) -> int | None:
    """Parse calorie string like '464 kcal' to integer."""
    if not cal_str:
        return None
    match = re.search(r"(\d+)\s*kcal", cal_str, re.IGNORECASE)
    if match:
        return int(match.group(1))
    return None


def _parse_rating(rating_str: str | None) -> float | None:
    """Parse rating from text like '4.5' or '5 (50)'."""
    if not rating_str:
        return None
    match = re.search(r"(\d+(?:[.,]\d+)?)", rating_str)
    if match:
        return float(match.group(1).replace(",", "."))
    return None


def _parse_health_score(score_str: str | None) -> int | None:
    """Parse health score from text."""
    if not score_str:
        return None
    match = re.search(r"(\d+)", score_str)
    if match:
        return int(match.group(1))
    return None


def _filter_by_meal_type(results: list[SearchResult], meal_type: str) -> list[SearchResult]:
    """Filter results by meal type keywords in title or URL."""
    if meal_type not in MEAL_TYPE_KEYWORDS:
        return results

    keywords = MEAL_TYPE_KEYWORDS[meal_type]
    filtered = []

    for result in results:
        text = f"{result.title} {result.url}".lower()
        # Include if any keyword matches, or include all if no specific meal filter
        if any(kw in text for kw in keywords):
            filtered.append(result)

    # If filtering removes too many results, return original list
    return filtered if len(filtered) >= 3 else results


def _filter_by_max_time(results: list[SearchResult], max_time: int) -> list[SearchResult]:
    """Filter results by maximum preparation time."""
    filtered = []
    for result in results:
        # Use total time if available, otherwise prep time
        time_to_check = result.total_time_minutes or result.prep_time_minutes
        if time_to_check is None or time_to_check <= max_time:
            filtered.append(result)

    # If filtering removes too many results, return original list
    return filtered if len(filtered) >= 3 else results


def search_recipes(
    include_ingredients: list[str],
    meal_type: str | None = None,
    max_time: int | None = None,
    max_results: int = 20,
    use_cache: bool = True,
    headless: bool = True,
) -> list[SearchResult]:
    """Search for recipes on eatsmarter.de with specified filters.

    Args:
        include_ingredients: List of ingredients to include in search
        meal_type: Meal type filter ("Mittagessen", "Abendessen", "Frühstück", "Snacks")
        max_time: Maximum preparation time in minutes
        max_results: Maximum number of results to return
        use_cache: Whether to use cached results if available
        headless: Whether to run browser in headless mode

    Returns:
        List of SearchResult objects matching the search criteria
    """
    if not include_ingredients:
        raise ValueError("At least one ingredient is required")

    # Check cache first
    cache_key = _get_cache_key(include_ingredients, meal_type, max_time)
    if use_cache:
        cached = _get_cached_results(cache_key)
        if cached is not None:
            print(f"  [Cache] Using cached results ({len(cached)} recipes)")
            return cached[:max_results]

    # Import playwright here to avoid import errors if not installed
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise ImportError(
            "Playwright is required. Install with:\n"
            "  pip install playwright\n"
            "  playwright install chromium"
        )

    # Build search query
    query = " ".join(include_ingredients)

    results = []
    print(f"Searching eatsmarter.de for: {', '.join(include_ingredients)}")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            locale="de-DE",
        )
        page = context.new_page()

        try:
            # Navigate to the main recipe page
            page.goto(f"{BASE_URL}/rezepte", wait_until="domcontentloaded", timeout=30000)
            time.sleep(1)

            # Accept cookies if dialog appears
            try:
                cookie_button = page.locator('button:has-text("Akzeptieren"), #onetrust-accept-btn-handler')
                if cookie_button.is_visible(timeout=3000):
                    cookie_button.click()
                    time.sleep(0.5)
            except Exception:
                pass

            # Find and use the search input
            search_input = page.locator('input[type="search"], input[name="query"], input[placeholder*="Suche"], #edit-search-api-fulltext').first
            if search_input.is_visible(timeout=5000):
                search_input.fill(query)
                time.sleep(0.3)
                search_input.press("Enter")
                print(f"  Submitted search query: {query}")
            else:
                # Fallback: try direct URL approach
                search_url = f"{SEARCH_URL}?query={quote_plus(query)}"
                print(f"  Fallback to URL: {search_url}")
                page.goto(search_url, wait_until="domcontentloaded", timeout=30000)

            # Wait for search results to load
            time.sleep(3)
            page.wait_for_load_state("networkidle", timeout=15000)

            # Find search result containers - they use teaser_search_result styling
            # Try multiple selector strategies
            result_containers = page.locator('[class*="teaser_search_result"], [class*="search-result"], .teaser-item').all()

            if not result_containers:
                # Fallback: find images with search result class and go to parent
                result_images = page.locator('img[class*="teaser_search_result"]').all()
                if result_images:
                    # Navigate up to find container elements
                    for img in result_images[:max_results * 2]:
                        try:
                            # Go up multiple levels to find the result container
                            container = img.locator("xpath=ancestor::*[.//a[contains(@href,'/rezepte/')]][1]").first
                            if container.is_visible():
                                result_containers.append(container)
                        except Exception:
                            continue

            # If still no containers, fall back to finding recipe links
            if not result_containers:
                recipe_links = page.locator("a[href*='/rezepte/']").all()
                print(f"  Found {len(recipe_links)} recipe links (fallback mode)")
            else:
                print(f"  Found {len(result_containers)} search result containers")

            seen_urls = set()

            # Process result containers or fall back to links
            items_to_process = result_containers if result_containers else []

            for item in items_to_process:
                if len(results) >= max_results * 2:
                    break

                try:
                    # Find the recipe link within this container
                    link = item.locator("a[href*='/rezepte/']").first
                    if not link.is_visible():
                        continue

                    url = link.get_attribute("href")
                    if not url:
                        continue

                    # Make URL absolute
                    if not url.startswith("http"):
                        url = f"{BASE_URL}{url}"

                    # Skip non-recipe pages
                    url_match = re.search(r"/rezepte/([a-z0-9-]+)/?$", url)
                    if not url_match:
                        continue

                    slug = url_match.group(1)
                    category_slugs = {
                        "saison", "ernaehrung", "klassiker", "gesundheit", "zutaten",
                        "mahlzeit", "region", "grundrezepte", "kochbuecher", "partnerrezepte",
                        "spezielles", "kochen", "backen", "getraenke", "vegan", "vegetarisch",
                        "low-carb", "fruehling", "sommer", "herbst", "winter",
                    }
                    if slug in category_slugs or "-" not in slug:
                        continue

                    # Deduplicate
                    if url in seen_urls:
                        continue
                    seen_urls.add(url)

                    # Get title - try multiple sources
                    title = link.text_content()
                    if not title or len(title.strip()) < 3:
                        title = link.get_attribute("title")
                    if not title or len(title.strip()) < 3:
                        # Extract from URL
                        title = slug.replace("-", " ").title()

                    if not title or len(title.strip()) < 3:
                        continue

                    title = title.strip()

                    # Skip non-recipe titles
                    skip_patterns = ["mehr", "alle rezepte", "zur übersicht", "weiter", "..."]
                    if any(p in title.lower() for p in skip_patterns):
                        continue

                    # Extract metadata from container text
                    container_text = item.text_content() or ""

                    prep_time = _parse_time(container_text)
                    calories = _parse_calories(container_text)
                    rating = _parse_rating(container_text)

                    # Look for health score (usually at the end, 1-100)
                    health_score = None
                    hs_match = re.search(r"\b(\d{1,2}|100)\s*$", container_text.strip())
                    if hs_match:
                        score = int(hs_match.group(1))
                        if 1 <= score <= 100:
                            health_score = score

                    # Get image URL
                    image_url = None
                    try:
                        img = item.locator("img").first
                        if img.is_visible():
                            image_url = img.get_attribute("src") or img.get_attribute("data-src")
                    except Exception:
                        pass

                    result = SearchResult(
                        title=title,
                        url=url,
                        prep_time_minutes=prep_time,
                        total_time_minutes=None,
                        calories=calories,
                        image_url=image_url,
                        rating=rating,
                        health_score=health_score,
                    )
                    results.append(result)

                except Exception:
                    continue

            # Fallback: if no results from containers, try direct link approach
            if not results:
                print("  Using fallback link extraction...")
                recipe_links = page.locator("a[href*='/rezepte/']").all()

                for link in recipe_links:
                    if len(results) >= max_results * 2:
                        break

                    try:
                        url = link.get_attribute("href")
                        if not url:
                            continue

                        if not url.startswith("http"):
                            url = f"{BASE_URL}{url}"

                        url_match = re.search(r"/rezepte/([a-z0-9-]+)/?$", url)
                        if not url_match or "-" not in url_match.group(1):
                            continue

                        if url in seen_urls:
                            continue
                        seen_urls.add(url)

                        title = link.text_content() or link.get_attribute("title")
                        if not title or len(title.strip()) < 3:
                            title = url_match.group(1).replace("-", " ").title()

                        result = SearchResult(
                            title=title.strip(),
                            url=url,
                        )
                        results.append(result)

                    except Exception:
                        continue

        except Exception as e:
            print(f"  [Error] Search failed: {e}")

        finally:
            browser.close()

    print(f"  Extracted {len(results)} unique recipes")

    # Apply filters
    if meal_type:
        results = _filter_by_meal_type(results, meal_type)
        print(f"  After meal type filter: {len(results)} recipes")

    if max_time:
        results = _filter_by_max_time(results, max_time)
        print(f"  After time filter: {len(results)} recipes")

    # Limit results
    results = results[:max_results]

    # Cache results
    if results:
        _cache_results(cache_key, results)
        print(f"  Cached {len(results)} results")

    return results


def clear_cache() -> int:
    """Clear all cached search results.

    Returns:
        Number of cache entries cleared
    """
    cache = _load_cache()
    count = len(cache)
    if CACHE_FILE.exists():
        CACHE_FILE.unlink()
    return count


def get_cache_stats() -> dict:
    """Get statistics about the search cache.

    Returns:
        Dict with cache statistics
    """
    cache = _load_cache()
    valid_entries = sum(1 for entry in cache.values() if _is_cache_valid(entry))
    total_results = sum(len(entry.get("results", [])) for entry in cache.values())

    return {
        "total_entries": len(cache),
        "valid_entries": valid_entries,
        "expired_entries": len(cache) - valid_entries,
        "total_cached_results": total_results,
        "cache_file": str(CACHE_FILE),
    }


if __name__ == "__main__":
    print("=" * 50)
    print("Eatsmarter Recipe Search Test")
    print("=" * 50)

    # Test search with some ingredients
    results = search_recipes(
        include_ingredients=["Tomate", "Mozzarella"],
        meal_type="Abendessen",
        max_time=45,
        headless=True,
    )

    print(f"\nFound {len(results)} recipes:")
    for i, r in enumerate(results, 1):
        time_str = f"{r.prep_time_minutes} min" if r.prep_time_minutes else "?"
        cal_str = f"{r.calories} kcal" if r.calories else "?"
        print(f"  {i}. {r.title} ({time_str}, {cal_str})")
        print(f"     URL: {r.url}")

    print("\nCache stats:")
    stats = get_cache_stats()
    for key, value in stats.items():
        print(f"  {key}: {value}")
