"""Playwright-based scraper for eatsmarter.de recipe search.

The search on eatsmarter.de relies on dynamic client-side loading, so this
module intentionally uses Playwright for real searches. To keep memory usage
stable in constrained environments, batch searches reuse a single browser,
context and page across multiple queries.
"""

import hashlib
import json
import os
import re
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from urllib.parse import quote_plus

from src.core.config import LOCAL_DIR, ensure_directories

CACHE_FILE = LOCAL_DIR / "search_cache.json"
CACHE_TTL_DAYS = 3

BASE_URL = "https://eatsmarter.de"
SEARCH_URL = f"{BASE_URL}/suche/rezepte"

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
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "SearchResult":
        return cls(**data)


def _get_cache_key(
    include_ingredients: list[str],
    meal_type: str | None,
    max_time: int | None,
) -> str:
    params = {
        "ingredients": sorted([i.lower().strip() for i in include_ingredients]),
        "meal_type": meal_type,
        "max_time": max_time,
    }
    return hashlib.md5(json.dumps(params, sort_keys=True).encode()).hexdigest()


def _load_cache() -> dict:
    if not CACHE_FILE.exists():
        return {}
    try:
        with open(CACHE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _save_cache(cache: dict) -> None:
    ensure_directories()
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


def _is_cache_valid(cache_entry: dict) -> bool:
    if "cached_at" not in cache_entry:
        return False
    cached_at = datetime.fromisoformat(cache_entry["cached_at"])
    return datetime.now() - cached_at < timedelta(days=CACHE_TTL_DAYS)


def _get_cached_results(cache_key: str) -> list[SearchResult] | None:
    cache = _load_cache()
    if cache_key in cache and _is_cache_valid(cache[cache_key]):
        return [SearchResult.from_dict(r) for r in cache[cache_key].get("results", [])]
    return None


def _cache_results(cache_key: str, results: list[SearchResult]) -> None:
    cache = _load_cache()
    cache[cache_key] = {
        "cached_at": datetime.now().isoformat(),
        "results": [r.to_dict() for r in results],
    }
    _save_cache(cache)


def _parse_time(time_str: str | None) -> int | None:
    if not time_str:
        return None
    total_minutes = 0
    hours_match = re.search(r"(\d+)\s*Std", time_str)
    if hours_match:
        total_minutes += int(hours_match.group(1)) * 60
    minutes_match = re.search(r"(\d+)\s*Min", time_str)
    if minutes_match:
        total_minutes += int(minutes_match.group(1))
    return total_minutes if total_minutes > 0 else None


def _parse_calories(cal_str: str | None) -> int | None:
    if not cal_str:
        return None
    match = re.search(r"(\d+)\s*kcal", cal_str, re.IGNORECASE)
    return int(match.group(1)) if match else None


def _parse_rating(rating_str: str | None) -> float | None:
    if not rating_str:
        return None
    match = re.search(r"(\d+(?:[.,]\d+)?)", rating_str)
    return float(match.group(1).replace(",", ".")) if match else None


def _is_recipe_url(url: str) -> bool:
    url_match = re.search(r"/rezepte/([a-z0-9-]+)/?$", url)
    if not url_match:
        return False
    slug = url_match.group(1)
    category_slugs = {
        "saison", "ernaehrung", "klassiker", "gesundheit", "zutaten",
        "mahlzeit", "region", "grundrezepte", "kochbuecher", "partnerrezepte",
        "spezielles", "kochen", "backen", "getraenke", "vegan", "vegetarisch",
        "low-carb", "fruehling", "sommer", "herbst", "winter",
    }
    return slug not in category_slugs and "-" in slug


def _title_from_url(url: str) -> str:
    return url.rstrip("/").split("/")[-1].replace("-", " ").title()


def _filter_by_meal_type(results: list[SearchResult], meal_type: str) -> list[SearchResult]:
    if meal_type not in MEAL_TYPE_KEYWORDS:
        return results
    keywords = MEAL_TYPE_KEYWORDS[meal_type]
    filtered = [r for r in results if any(kw in f"{r.title} {r.url}".lower() for kw in keywords)]
    return filtered if len(filtered) >= 3 else results


def _filter_by_max_time(results: list[SearchResult], max_time: int) -> list[SearchResult]:
    filtered = []
    for result in results:
        time_to_check = result.total_time_minutes or result.prep_time_minutes
        if time_to_check is None or time_to_check <= max_time:
            filtered.append(result)
    return filtered if len(filtered) >= 3 else results


def _create_browser_resources(headless: bool):
    from playwright.sync_api import sync_playwright

    playwright = sync_playwright().start()
    chromium_path = os.getenv("PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH")
    launch_kwargs = {
        "headless": headless,
        "args": [
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu",
            "--disable-extensions",
            "--disable-background-networking",
            "--disable-background-timer-throttling",
            "--disable-renderer-backgrounding",
            "--mute-audio",
        ],
    }
    if chromium_path:
        launch_kwargs["executable_path"] = chromium_path

    browser = playwright.chromium.launch(**launch_kwargs)
    context = browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        locale="de-DE",
    )
    context.route(
        "**/*",
        lambda route: route.abort()
        if route.request.resource_type in {"image", "media", "font"}
        else route.continue_(),
    )
    page = context.new_page()
    return playwright, browser, context, page


def _accept_cookies_if_present(page) -> None:
    try:
        cookie_button = page.locator(
            'button:has-text("Akzeptieren"), #onetrust-accept-btn-handler'
        )
        if cookie_button.is_visible(timeout=3000):
            cookie_button.click()
            time.sleep(0.5)
    except Exception:
        pass


def _extract_search_results_from_page(page, max_results: int) -> list[SearchResult]:
    results: list[SearchResult] = []
    seen_urls: set[str] = set()

    result_containers = page.locator(
        "[class*='teaser_search_result'], [class*='search-result'], .teaser-item"
    ).all()
    if not result_containers:
        recipe_links = page.locator("a[href*='/rezepte/']").all()
        print(f"  Found {len(recipe_links)} recipe links (fallback mode)")
    else:
        print(f"  Found {len(result_containers)} search result containers")

    items_to_process = result_containers if result_containers else []
    for item in items_to_process:
        if len(results) >= max_results * 2:
            break
        try:
            link = item.locator("a[href*='/rezepte/']").first
            if not link.is_visible():
                continue
            url = link.get_attribute("href")
            if not url:
                continue
            if not url.startswith("http"):
                url = f"{BASE_URL}{url}"
            if not _is_recipe_url(url) or url in seen_urls:
                continue
            seen_urls.add(url)

            title = link.text_content() or link.get_attribute("title") or _title_from_url(url)
            title = title.strip()
            if len(title) < 3:
                continue

            container_text = item.text_content() or ""
            results.append(
                SearchResult(
                    title=title,
                    url=url,
                    prep_time_minutes=_parse_time(container_text),
                    calories=_parse_calories(container_text),
                    rating=_parse_rating(container_text),
                )
            )
        except Exception:
            continue

    if results:
        return results

    print("  Using fallback link extraction...")
    for link in page.locator("a[href*='/rezepte/']").all():
        if len(results) >= max_results * 2:
            break
        try:
            url = link.get_attribute("href")
            if not url:
                continue
            if not url.startswith("http"):
                url = f"{BASE_URL}{url}"
            if not _is_recipe_url(url) or url in seen_urls:
                continue
            seen_urls.add(url)
            title = link.text_content() or link.get_attribute("title") or _title_from_url(url)
            results.append(SearchResult(title=title.strip(), url=url))
        except Exception:
            continue

    return results


def _run_playwright_search(page, query: str, max_results: int) -> list[SearchResult]:
    search_url = f"{SEARCH_URL}?query={quote_plus(query)}"
    page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
    _accept_cookies_if_present(page)
    time.sleep(3)
    page.wait_for_load_state("networkidle", timeout=15000)
    return _extract_search_results_from_page(page, max_results)


def search_recipes_batch(
    searches: list[dict],
    *,
    headless: bool = True,
    use_cache: bool = True,
) -> list[list[SearchResult]]:
    """Run multiple eatsmarter searches while reusing a single browser session."""
    prepared: list[dict] = []
    for search in searches:
        include_ingredients = search["include_ingredients"]
        meal_type = search.get("meal_type")
        max_time = search.get("max_time")
        max_results = search.get("max_results", 20)

        cache_key = _get_cache_key(include_ingredients, meal_type, max_time)
        cached = _get_cached_results(cache_key) if use_cache else None
        prepared.append(
            {
                "include_ingredients": include_ingredients,
                "meal_type": meal_type,
                "max_time": max_time,
                "max_results": max_results,
                "cache_key": cache_key,
                "cached": cached,
            }
        )

    if all(item["cached"] is not None for item in prepared):
        return [item["cached"][: item["max_results"]] for item in prepared]

    playwright = browser = context = page = None
    try:
        playwright, browser, context, page = _create_browser_resources(headless=headless)
        all_results: list[list[SearchResult]] = []

        for item in prepared:
            if item["cached"] is not None:
                print(f"  [Cache] Using cached results ({len(item['cached'])} recipes)")
                all_results.append(item["cached"][: item["max_results"]])
                continue

            ingredients = item["include_ingredients"]
            query = " ".join(ingredients)
            print(f"Searching eatsmarter.de for: {', '.join(ingredients)}")

            results = _run_playwright_search(page, query, item["max_results"])
            print(f"  Extracted {len(results)} unique recipes")

            if item["meal_type"]:
                results = _filter_by_meal_type(results, item["meal_type"])
                print(f"  After meal type filter: {len(results)} recipes")
            if item["max_time"]:
                results = _filter_by_max_time(results, item["max_time"])
                print(f"  After time filter: {len(results)} recipes")

            results = results[: item["max_results"]]
            if results:
                _cache_results(item["cache_key"], results)
                print(f"  Cached {len(results)} results")

            all_results.append(results)
            time.sleep(0.5)

        return all_results
    finally:
        if page is not None:
            page.close()
        if context is not None:
            context.close()
        if browser is not None:
            browser.close()
        if playwright is not None:
            playwright.stop()


def search_recipes(
    include_ingredients: list[str],
    meal_type: str | None = None,
    max_time: int | None = None,
    max_results: int = 20,
    use_cache: bool = True,
    headless: bool = True,
) -> list[SearchResult]:
    """Search for recipes on eatsmarter.de with specified filters."""
    return search_recipes_batch(
        [
            {
                "include_ingredients": include_ingredients,
                "meal_type": meal_type,
                "max_time": max_time,
                "max_results": max_results,
            }
        ],
        headless=headless,
        use_cache=use_cache,
    )[0]


def clear_cache() -> int:
    cache = _load_cache()
    count = len(cache)
    if CACHE_FILE.exists():
        CACHE_FILE.unlink()
    return count


def get_cache_stats() -> dict:
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
