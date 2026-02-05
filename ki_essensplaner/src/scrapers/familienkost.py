"""Custom scraper for familienkost.de using JSON-LD structured data.

This scraper is needed because familienkost.de is not supported by the
recipe-scrapers library. It extracts recipe data from Schema.org JSON-LD
structured data embedded in the page.

Features:
- Extracts title, ingredients, instructions, prep time
- Extracts nutrition data (calories, fat, protein, carbs)
- Decodes HTML entities in German text (e.g., &ouml; → ö)
- Parses ISO 8601 durations (PT20M → 20 minutes)

The JSON-LD structure on familienkost.de:
    <script type="application/ld+json">
    {
        "@type": "Recipe",
        "name": "Eierragout",
        "recipeIngredient": ["1 Zwiebel", "50 g Butter", ...],
        "recipeInstructions": [...],
        "nutrition": {"calories": "374 kcal", ...}
    }
    </script>

Example usage:
    >>> from src.scrapers.familienkost import scrape_familienkost
    >>> recipe = scrape_familienkost("https://www.familienkost.de/rezept_eierragout.html")
    >>> print(recipe.title, recipe.calories)
    Eierragout 374
"""

import html
import json
import re
from dataclasses import dataclass

import requests
from bs4 import BeautifulSoup

from src.models.recipe import RecipeCreate


@dataclass
class FamilienkostScraper:
    """Scraper for familienkost.de recipes using Schema.org JSON-LD.

    Attributes:
        url: The recipe URL to scrape
        _data: Cached JSON-LD data (lazy-loaded on first access)
    """

    url: str
    _data: dict | None = None

    def _fetch_and_parse(self) -> dict | None:
        """Fetch the page and extract JSON-LD recipe data."""
        if self._data is not None:
            return self._data

        try:
            response = requests.get(self.url, timeout=10)
            response.raise_for_status()
        except requests.RequestException as e:
            print(f"  [X] Error fetching {self.url}: {e}")
            return None

        soup = BeautifulSoup(response.text, "html.parser")

        # Find JSON-LD script tags
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string)
                # Handle @graph structure
                if "@graph" in data:
                    for item in data["@graph"]:
                        if item.get("@type") == "Recipe":
                            self._data = item
                            return self._data
                # Direct Recipe type
                if data.get("@type") == "Recipe":
                    self._data = data
                    return self._data
            except json.JSONDecodeError:
                continue

        print(f"  [X] No JSON-LD recipe data found: {self.url}")
        return None

    def title(self) -> str:
        """Get the recipe title."""
        data = self._fetch_and_parse()
        title = data.get("name", "") if data else ""
        return html.unescape(title)

    def total_time(self) -> int | None:
        """Get total time in minutes (prep + cook)."""
        data = self._fetch_and_parse()
        if not data:
            return None

        # Try totalTime first
        total = data.get("totalTime")
        if total:
            return self._parse_duration(total)

        # Fall back to prepTime + cookTime
        prep = data.get("prepTime")
        cook = data.get("cookTime")
        prep_mins = self._parse_duration(prep) if prep else 0
        cook_mins = self._parse_duration(cook) if cook else 0

        return (prep_mins + cook_mins) if (prep_mins or cook_mins) else None

    def _parse_duration(self, duration: str) -> int:
        """Parse ISO 8601 duration (PT20M, PT1H30M) to minutes."""
        if not duration:
            return 0

        # Match hours and minutes
        hours = 0
        minutes = 0

        h_match = re.search(r"(\d+)H", duration)
        m_match = re.search(r"(\d+)M", duration)

        if h_match:
            hours = int(h_match.group(1))
        if m_match:
            minutes = int(m_match.group(1))

        return hours * 60 + minutes

    def ingredients(self) -> list[str]:
        """Get list of ingredients."""
        data = self._fetch_and_parse()
        if not data:
            return []

        ingredients = data.get("recipeIngredient", [])
        # Decode HTML entities (e.g., &ouml; -> ö, &#189; -> ½)
        return [html.unescape(ing.strip()) for ing in ingredients if ing.strip()]

    def nutrients(self) -> dict:
        """Get nutrition information.

        Returns:
            Dict with calories, fat_g, protein_g, carbs_g (as floats)
        """
        data = self._fetch_and_parse()
        if not data:
            return {}

        nutrition = data.get("nutrition", {})
        if not nutrition:
            return {}

        result = {}

        # Parse calories (e.g., "374 kcal" -> 374)
        calories = nutrition.get("calories", "")
        if calories:
            match = re.search(r"(\d+)", calories)
            if match:
                result["calories"] = int(match.group(1))

        # Parse grams (e.g., "22 g" -> 22.0)
        for key, result_key in [
            ("fatContent", "fat_g"),
            ("proteinContent", "protein_g"),
            ("carbohydrateContent", "carbs_g"),
        ]:
            value = nutrition.get(key, "")
            if value:
                match = re.search(r"(\d+(?:[.,]\d+)?)", value)
                if match:
                    result[result_key] = float(match.group(1).replace(",", "."))

        return result

    def instructions(self) -> str:
        """Get cooking instructions as text."""
        data = self._fetch_and_parse()
        if not data:
            return ""

        instructions = data.get("recipeInstructions", [])

        # Handle different formats
        if isinstance(instructions, str):
            return html.unescape(instructions)

        if isinstance(instructions, list):
            steps = []
            for i, step in enumerate(instructions, 1):
                if isinstance(step, dict):
                    text = step.get("text", "")
                else:
                    text = str(step)
                if text.strip():
                    steps.append(f"{i}. {html.unescape(text.strip())}")
            return "\n".join(steps)

        return ""


def scrape_familienkost(url: str) -> RecipeCreate | None:
    """Scrape a recipe from familienkost.de.

    Args:
        url: The familienkost.de recipe URL

    Returns:
        RecipeCreate model or None if scraping failed
    """
    scraper = FamilienkostScraper(url)

    title = scraper.title()
    if not title:
        return None

    nutrients = scraper.nutrients()

    return RecipeCreate(
        title=title,
        source="familienkost",
        source_url=url,
        prep_time_minutes=scraper.total_time(),
        ingredients=scraper.ingredients(),
        instructions=scraper.instructions(),
        calories=nutrients.get("calories"),
        fat_g=nutrients.get("fat_g"),
        protein_g=nutrients.get("protein_g"),
        carbs_g=nutrients.get("carbs_g"),
    )


if __name__ == "__main__":
    # Test with a sample URL
    test_url = "https://www.familienkost.de/rezept_eierragout.html"
    print(f"Testing: {test_url}")
    print("=" * 50)

    recipe = scrape_familienkost(test_url)
    if recipe:
        print(f"Title: {recipe.title}")
        print(f"Time: {recipe.prep_time_minutes} min")
        print(f"Ingredients ({len(recipe.ingredients)}):")
        for ing in recipe.ingredients[:5]:
            print(f"  - {ing}")
        if len(recipe.ingredients) > 5:
            print(f"  ... and {len(recipe.ingredients) - 5} more")
        print(f"Instructions: {recipe.instructions[:200]}...")
    else:
        print("Failed to scrape recipe")
