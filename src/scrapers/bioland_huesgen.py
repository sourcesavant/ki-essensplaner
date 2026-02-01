"""Scraper for bioland-huesgen.de to get currently available seasonal products.

This scraper fetches product availability from the Bioland Hüsgen farm shop,
which offers seasonal organic fruits, vegetables, and herbs. The product
availability changes weekly based on season.

Categories scraped:
- Gemüse & Pilze (vegetables & mushrooms)
- Salate & Schnittkräuter (salads & herbs)
- Obst, Nüsse & Saaten (fruits, nuts & seeds)
- Kartoffeln & Süßkartoffeln (potatoes & sweet potatoes)

The scraper extracts product names from h3 > a elements and normalizes them
using the existing GPT-based ingredient categorizer to enable matching with
recipe ingredients.

Example usage:
    >>> from src.scrapers.bioland_huesgen import scrape_available_products, refresh_available_products
    >>> products = scrape_available_products()
    >>> print(f"Found {len(products)} products")
    >>> refresh_available_products()  # Scrape, normalize, and save to DB
    >>> ensure_bioland_current()  # Auto-update if data is older than 7 days
"""

import html
import re
import time
from datetime import datetime, timedelta

import requests
from bs4 import BeautifulSoup

from src.core.database import (
    add_available_products_batch,
    clear_available_products,
    get_connection,
    init_db,
)

SOURCE_NAME = "bioland_huesgen"

# Update interval in days (weekly refresh for seasonal products)
BIOLAND_UPDATE_INTERVAL_DAYS = 7

CATEGORY_URLS = {
    "gemüse_pilze": "https://www.bioland-huesgen.de/m/vom-acker/gemuese-pilze?path=/n_19/g_110",
    "salate_kräuter": "https://www.bioland-huesgen.de/m/vom-acker/salate-schnittkraeuter?path=/n_19/g_111",
    "kartoffeln": "https://www.bioland-huesgen.de/m/vom-acker/kartoffeln-suesskartoffeln?path=/n_19/g_112",
    "obst_nüsse": "https://www.bioland-huesgen.de/m/vom-acker/obst-nuesse-saaten?path=/n_19/g_113",
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}


def _clean_product_name(name: str) -> str:
    """Clean and normalize a product name.

    Removes quantity info, weight specs, and other noise while preserving
    the core product name for normalization.

    Args:
        name: Raw product name from website

    Returns:
        Cleaned product name
    """
    # Decode HTML entities
    name = html.unescape(name.strip())

    # Remove common suffixes/prefixes that don't help with matching
    patterns_to_remove = [
        r"\s*[\d,]+\s*kg\s*(?:Kiste)?",  # "3kg Kiste", "12,5kg"
        r"\s*[\d,]+\s*g\b",  # "100 g", "250g"
        r"\s*ca\.?\s*[\d,]*-?[\d,]*\s*(?:kg|g)?\b",  # "ca. 400 g", "ca.200-400g", "ca.1", "ca."
        r"\s*\(ca\.?\s*[\d,]+\s*(?:kg|g)?\)",  # "(ca. 100 g)"
        r"\s*\([\d,]+\s*(?:kg|g)\)",  # "(100 g)"
        r"\s*Cal\.?\s*[\d-]+(?:er)?",  # "Cal.4-5", "Cal. 46er"
        r"\s*\|\s*[\w\s]+$",  # "| Hüsgen", "| Bois"
        r"\s*Top Qualität!?",
        r"\s*Fair Trade",
        r"\s*aus Deutschland",
        r"\s*aus Peru",
        r"\s*wöchentl\.\s*wechselnd",
        r"\s*im Bund",
        r"\s*Sorte\s+\w+",  # "Sorte Hicaz"
        r"\s*\d+er$",  # "46er"
        r"\s*–.*$",  # "– frisch & würzig", "– ideal für..."
        r"\s*-\s*geputzt",
        r"\s*frisch\s*$",
        r"\s*,\s*[\d,]+\s*kg\s*\w*$",  # ", 2 kg festkochend"
        r"\s*,\s*(festkochend|mehlig|vorwiegend festkochend|rotschalig).*$",
    ]

    for pattern in patterns_to_remove:
        name = re.sub(pattern, "", name, flags=re.IGNORECASE)

    # Remove empty parentheses and brackets
    name = re.sub(r"\s*\(\s*-?\s*\)", "", name)
    name = re.sub(r"\s*\[\s*\]", "", name)

    # Remove trailing numbers/fragments
    name = re.sub(r"\s*-\s*\d+$", "", name)

    # Clean up whitespace and trailing punctuation
    name = " ".join(name.split())
    name = name.strip(" -–,.()[]")

    return name


def scrape_category(url: str) -> list[str]:
    """Scrape product names from a single category page.

    Args:
        url: Category page URL

    Returns:
        List of product names found on the page
    """
    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        response.raise_for_status()
    except requests.RequestException as e:
        print(f"  [X] Error fetching {url}: {e}")
        return []

    soup = BeautifulSoup(response.text, "html.parser")
    products = []

    # Products are in h3 > a tags
    for h3 in soup.find_all("h3"):
        link = h3.find("a")
        if link and link.text.strip():
            # Only include product links (contain /p/ in href)
            href = link.get("href", "")
            if "/p/" in href:
                product_name = link.text.strip()
                products.append(product_name)

    return products


def scrape_available_products() -> list[dict]:
    """Scrape all available products from all categories.

    Returns:
        List of dicts with 'product_name', 'cleaned_name', and 'category' keys
    """
    all_products = []

    print("Scraping Bioland Hüsgen products...")

    for category, url in CATEGORY_URLS.items():
        print(f"  Scraping {category}...")
        products = scrape_category(url)

        for product in products:
            cleaned = _clean_product_name(product)
            all_products.append({
                "source": SOURCE_NAME,
                "product_name": product,
                "cleaned_name": cleaned,
                "category": category,
            })

        print(f"    Found {len(products)} products")
        time.sleep(0.5)  # Rate limiting

    print(f"Total: {len(all_products)} products")
    return all_products


def refresh_available_products(normalize: bool = True) -> dict:
    """Scrape products and update the database.

    This function:
    1. Scrapes all product names from bioland-huesgen.de
    2. Optionally normalizes them using GPT categorizer
    3. Clears old products and saves new ones to DB

    Args:
        normalize: If True, use GPT to normalize product names to base ingredients

    Returns:
        Dict with statistics: products_found, products_saved, normalized
    """
    init_db()

    # Scrape products
    products = scrape_available_products()

    if not products:
        return {"products_found": 0, "products_saved": 0, "normalized": False}

    # Normalize if requested
    if normalize:
        print("Normalizing product names...")
        products = _normalize_products(products)

    # Clear old products and save new ones
    deleted = clear_available_products(SOURCE_NAME)
    if deleted:
        print(f"  Cleared {deleted} old products")

    # Prepare for batch insert
    db_products = [
        {
            "source": p["source"],
            "product_name": p["product_name"],
            "base_ingredient": p.get("base_ingredient"),
            "category": p["category"],
        }
        for p in products
    ]

    saved = add_available_products_batch(db_products)
    print(f"  Saved {saved} products to database")

    return {
        "products_found": len(products),
        "products_saved": saved,
        "normalized": normalize,
    }


def _normalize_products(products: list[dict]) -> list[dict]:
    """Normalize product names using GPT categorizer.

    Uses the same categorization system as recipe ingredients to ensure
    consistent matching between recipes and available products.
    """
    from src.profile.ingredient_categorizer import categorize_ingredients_batch

    # Get unique cleaned names for categorization
    cleaned_names = list({p["cleaned_name"] for p in products})

    print(f"  Categorizing {len(cleaned_names)} unique product names...")

    # Get base ingredients from GPT
    # Returns dict: {"ingredient": {"name_normalized": "...", "base_ingredient": "..."}}
    categories = categorize_ingredients_batch(cleaned_names)

    # Apply to products
    for product in products:
        cleaned = product["cleaned_name"]
        cat_data = categories.get(cleaned, {})
        if isinstance(cat_data, dict):
            product["base_ingredient"] = cat_data.get("base_ingredient", cleaned.lower())
        else:
            product["base_ingredient"] = cleaned.lower()

    return products


def get_bioland_data_age() -> timedelta | None:
    """Get the age of the Bioland product data.

    Returns:
        timedelta since last scrape, or None if no data exists
    """
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT MAX(scraped_at) as last_scraped
            FROM available_products
            WHERE source = ?
            """,
            (SOURCE_NAME,),
        ).fetchone()

        if row and row["last_scraped"]:
            last_scraped = datetime.fromisoformat(row["last_scraped"])
            return datetime.now() - last_scraped

    return None


def is_bioland_data_outdated(max_age_days: int = BIOLAND_UPDATE_INTERVAL_DAYS) -> bool:
    """Check if the Bioland product data needs updating.

    Args:
        max_age_days: Maximum age in days before data is considered outdated

    Returns:
        True if data is outdated or doesn't exist, False otherwise
    """
    age = get_bioland_data_age()

    if age is None:
        return True

    return age > timedelta(days=max_age_days)


def ensure_bioland_current(
    force: bool = False,
    max_age_days: int = BIOLAND_UPDATE_INTERVAL_DAYS,
) -> tuple[int, bool]:
    """Ensure Bioland product data is current, refreshing if needed.

    This is the main entry point for agents that need Bioland availability.
    It checks if the data exists and is recent enough, refreshing if necessary.

    Args:
        force: Force refresh even if data is current
        max_age_days: Maximum age in days before triggering update

    Returns:
        Tuple of (product_count, was_updated)
        - product_count: Number of products in database
        - was_updated: True if data was refreshed
    """
    if force:
        print("Forcing Bioland data refresh...")
        result = refresh_available_products(normalize=True)
        return result["products_saved"], True

    if is_bioland_data_outdated(max_age_days):
        age = get_bioland_data_age()
        if age is None:
            print("No Bioland data found. Scraping...")
        else:
            print(f"Bioland data is {age.days} days old. Refreshing...")

        result = refresh_available_products(normalize=True)
        return result["products_saved"], True

    # Data is current - just count existing products
    with get_connection() as conn:
        row = conn.execute(
            "SELECT COUNT(*) as count FROM available_products WHERE source = ?",
            (SOURCE_NAME,),
        ).fetchone()
        count = row["count"] if row else 0

    return count, False


if __name__ == "__main__":
    print("=" * 50)
    print("Bioland Hüsgen Product Scraper")
    print("=" * 50)

    result = refresh_available_products(normalize=True)

    print("\nResults:")
    print(f"  Products found: {result['products_found']}")
    print(f"  Products saved: {result['products_saved']}")
    print(f"  Normalized: {result['normalized']}")
