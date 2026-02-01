"""Seasonality logic for German ingredients.

This module provides functions to check whether ingredients are in season
based on the current month. It uses a calendar of typical German produce
with their available months.

Ingredients not in the calendar are considered available year-round.

Example usage:
    >>> from src.scoring.seasonality import is_in_season, get_out_of_season_ingredients
    >>> is_in_season("spargel", month=5)  # May
    True
    >>> is_in_season("spargel", month=8)  # August
    False
    >>> get_out_of_season_ingredients(["spargel", "kartoffel"], month=8)
    ["spargel"]
"""

import json
from datetime import date

from src.core.config import DATA_DIR

# Path to external seasonal data (optional override)
SEASONAL_DATA_FILE = DATA_DIR / "local" / "seasonal_ingredients.json"

# Default seasonal calendar for German produce
# Month numbers: 1=January, 12=December
# List contains months when the ingredient is in season
SEASONAL_CALENDAR: dict[str, list[int]] = {
    # Gemüse mit klarer Saison
    "spargel": [4, 5, 6],  # April-Juni
    "rhabarber": [4, 5, 6],  # April-Juni
    "bärlauch": [3, 4, 5],  # März-Mai
    "radieschen": [4, 5, 6, 7, 8, 9],  # April-September
    "kohlrabi": [5, 6, 7, 8, 9, 10],  # Mai-Oktober
    "erbse": [6, 7, 8],  # Juni-August
    "bohne": [7, 8, 9],  # Juli-September
    "zucchini": [6, 7, 8, 9, 10],  # Juni-Oktober
    "tomate": [7, 8, 9, 10],  # Juli-Oktober (Freiland)
    "paprika": [7, 8, 9, 10],  # Juli-Oktober
    "gurke": [6, 7, 8, 9],  # Juni-September
    "aubergine": [7, 8, 9, 10],  # Juli-Oktober
    "mais": [8, 9, 10],  # August-Oktober
    "kürbis": [9, 10, 11, 12],  # September-Dezember
    "hokkaido": [9, 10, 11, 12],  # September-Dezember
    "butternut": [9, 10, 11, 12],  # September-Dezember

    # Kohl (Herbst/Winter)
    "rosenkohl": [10, 11, 12, 1, 2],  # Oktober-Februar
    "grünkohl": [11, 12, 1, 2],  # November-Februar
    "wirsing": [9, 10, 11, 12, 1, 2, 3],  # September-März
    "rotkohl": [9, 10, 11, 12, 1, 2, 3],  # September-März
    "weißkohl": [9, 10, 11, 12, 1, 2, 3],  # September-März
    "chinakohl": [9, 10, 11, 12],  # September-Dezember

    # Salate
    "feldsalat": [10, 11, 12, 1, 2, 3],  # Oktober-März
    "rucola": [5, 6, 7, 8, 9, 10],  # Mai-Oktober
    "kopfsalat": [5, 6, 7, 8, 9],  # Mai-September
    "eisbergsalat": [6, 7, 8, 9],  # Juni-September

    # Obst
    "erdbeere": [5, 6, 7],  # Mai-Juli
    "himbeere": [6, 7, 8],  # Juni-August
    "heidelbeere": [7, 8, 9],  # Juli-September
    "brombeere": [7, 8, 9],  # Juli-September
    "johannisbeere": [6, 7, 8],  # Juni-August
    "stachelbeere": [6, 7],  # Juni-Juli
    "kirsche": [6, 7],  # Juni-Juli
    "pflaume": [7, 8, 9],  # Juli-September
    "zwetschge": [8, 9, 10],  # August-Oktober
    "aprikose": [7, 8],  # Juli-August
    "pfirsich": [7, 8, 9],  # Juli-September
    "birne": [8, 9, 10, 11],  # August-November
    "apfel": [8, 9, 10, 11, 12, 1, 2, 3],  # August-März (Lagerware)
    "quitte": [9, 10, 11],  # September-November
    "traube": [9, 10],  # September-Oktober

    # Ganzjährig verfügbar (Lagerware/Gewächshaus)
    "kartoffel": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12],
    "möhre": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12],
    "karotte": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12],
    "zwiebel": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12],
    "knoblauch": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12],
    "sellerie": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12],
    "lauch": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12],
    "porree": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12],
    "rote bete": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12],
    "pastinake": [10, 11, 12, 1, 2, 3],  # Oktober-März
    "schwarzwurzel": [10, 11, 12, 1, 2, 3],  # Oktober-März
    "topinambur": [10, 11, 12, 1, 2, 3],  # Oktober-März

    # Pilze (Hauptsaison, aber teils ganzjährig aus Zucht)
    "steinpilz": [8, 9, 10, 11],  # August-November
    "pfifferling": [6, 7, 8, 9, 10],  # Juni-Oktober
    "champignon": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12],  # Zucht ganzjährig

    # Kräuter (Freiland-Saison, Gewächshaus ganzjährig)
    "basilikum": [6, 7, 8, 9],  # Juni-September (Freiland)
    "dill": [5, 6, 7, 8, 9],  # Mai-September
    "koriander": [5, 6, 7, 8, 9],  # Mai-September
    "minze": [5, 6, 7, 8, 9, 10],  # Mai-Oktober
}


def _load_external_data() -> dict[str, list[int]] | None:
    """Load seasonal data from external JSON file if it exists."""
    if SEASONAL_DATA_FILE.exists():
        try:
            with open(SEASONAL_DATA_FILE, encoding="utf-8") as f:
                data = json.load(f)
                return data.get("ingredients", data)
        except (json.JSONDecodeError, KeyError):
            return None
    return None


def _get_calendar() -> dict[str, list[int]]:
    """Get the seasonal calendar, preferring external data if available."""
    external = _load_external_data()
    if external:
        # Merge: external data overrides defaults
        merged = SEASONAL_CALENDAR.copy()
        merged.update(external)
        return merged
    return SEASONAL_CALENDAR


def is_in_season(ingredient: str, month: int | None = None) -> bool | None:
    """Check if an ingredient is in season.

    Args:
        ingredient: Normalized ingredient name (lowercase)
        month: Month number (1-12). Defaults to current month.

    Returns:
        True if in season, False if not in season, None if no data available
        (ingredient not in calendar = assumed year-round = True)
    """
    if month is None:
        month = date.today().month

    if not 1 <= month <= 12:
        raise ValueError(f"Month must be 1-12, got {month}")

    ingredient = ingredient.lower().strip()
    calendar = _get_calendar()

    if ingredient not in calendar:
        # Unknown ingredient = assume year-round availability
        return None

    return month in calendar[ingredient]


def get_out_of_season_ingredients(
    ingredients: list[str],
    month: int | None = None,
) -> list[str]:
    """Get list of ingredients that are not in season.

    Args:
        ingredients: List of normalized ingredient names
        month: Month number (1-12). Defaults to current month.

    Returns:
        List of ingredients that are definitely not in season.
        Ingredients without data are NOT included (assumed available).
    """
    if month is None:
        month = date.today().month

    out_of_season = []
    for ingredient in ingredients:
        result = is_in_season(ingredient, month)
        if result is False:  # Explicitly False, not None
            out_of_season.append(ingredient)

    return out_of_season


def get_seasonal_ingredients(month: int | None = None) -> list[str]:
    """Get list of all ingredients that are in season for a given month.

    Args:
        month: Month number (1-12). Defaults to current month.

    Returns:
        List of ingredient names that are in season.
    """
    if month is None:
        month = date.today().month

    calendar = _get_calendar()
    return [
        ingredient
        for ingredient, months in calendar.items()
        if month in months
    ]


def get_season_score(
    ingredients: list[str],
    month: int | None = None,
) -> float:
    """Calculate a seasonality score for a list of ingredients.

    Args:
        ingredients: List of normalized ingredient names
        month: Month number (1-12). Defaults to current month.

    Returns:
        Score from 0.0 to 1.0 where:
        - 1.0 = all ingredients are in season or year-round
        - 0.0 = all ingredients are out of season
    """
    if not ingredients:
        return 1.0

    if month is None:
        month = date.today().month

    scores = []
    for ingredient in ingredients:
        result = is_in_season(ingredient, month)
        if result is None:
            # Unknown = assume available = 1.0
            scores.append(1.0)
        elif result:
            scores.append(1.0)
        else:
            scores.append(0.0)

    return sum(scores) / len(scores)


if __name__ == "__main__":
    # Test the module
    current_month = date.today().month
    month_names = [
        "", "Januar", "Februar", "März", "April", "Mai", "Juni",
        "Juli", "August", "September", "Oktober", "November", "Dezember"
    ]

    print(f"Aktueller Monat: {month_names[current_month]}")
    print()

    # Test specific ingredients
    test_ingredients = ["spargel", "erdbeere", "kartoffel", "kürbis", "tomate"]
    print("Saisonalitäts-Check:")
    for ing in test_ingredients:
        result = is_in_season(ing, current_month)
        status = "in Saison" if result else ("nicht in Saison" if result is False else "unbekannt")
        print(f"  {ing}: {status}")

    print()

    # Test out of season detection
    recipe_ingredients = ["spargel", "kartoffel", "tomate", "zwiebel"]
    out_of_season = get_out_of_season_ingredients(recipe_ingredients, 8)  # August
    print(f"Nicht saisonal im August: {out_of_season}")

    # Test seasonal ingredients for current month
    seasonal = get_seasonal_ingredients(current_month)
    print(f"\nSaisonale Zutaten ({month_names[current_month]}): {len(seasonal)}")
    print(f"  Beispiele: {seasonal[:10]}")
