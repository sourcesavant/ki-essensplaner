"""Check if excluded ingredients can be replaced in recipes using GPT-4o-mini.

This module uses GPT to determine if an excluded ingredient is a main ingredient
(not replaceable) or a side ingredient (replaceable with alternatives).

Results are cached to avoid repeated API calls for the same ingredient-recipe
combinations. The cache is stored in data/local/replacement_cache.json.

Example usage:
    >>> from src.profile.ingredient_replacer import check_ingredient_replaceable
    >>> result = check_ingredient_replaceable(
    ...     ingredient="paprika",
    ...     recipe_name="Gemüsepfanne",
    ...     all_ingredients=["Paprika", "Zucchini", "Zwiebel", "Knoblauch"]
    ... )
    >>> print(result)
    {"replaceable": True, "alternatives": ["Zucchini", "Karotte"]}

Issue #18: User kann Zutaten ausschließen
"""

import hashlib
import json
import os
from pathlib import Path

from openai import OpenAI

from src.core.config import DATA_DIR

# Cache file for replacement checks
REPLACEMENT_CACHE_FILE = DATA_DIR / "local" / "replacement_cache.json"

SYSTEM_PROMPT = """Du bist ein Experte für Kochen und Zutatenersatz.

Deine Aufgabe ist zu beurteilen, ob eine Zutat in einem Rezept ersetzbar ist.

**Hauptzutat (nicht ersetzbar):**
- Die Zutat ist namensgebend (z.B. "Paprika" in "Gefüllte Paprika")
- Die Zutat ist mengenmäßig dominant
- Die Zutat bestimmt den Charakter des Gerichts
- Ohne die Zutat wäre es ein völlig anderes Gericht

**Nebenzutat (ersetzbar):**
- Die Zutat ist eine von vielen gleichwertigen Zutaten
- Die Zutat dient der Würzung oder Dekoration
- Die Zutat kann durch ähnliche Zutaten ersetzt werden

Antworte NUR mit einem JSON-Objekt, keine Erklärungen."""

USER_PROMPT_TEMPLATE = """Zutat "{ingredient}" soll ausgeschlossen werden.

Rezept: {recipe_name}
Zutaten: {ingredients_list}

Ist "{ingredient}" hier eine Hauptzutat (nicht ersetzbar) oder Nebenzutat (ersetzbar)?
Wenn ersetzbar: Schlage 2-3 passende Alternativen vor, die zum Rezept passen.

Antwort als JSON:
{{"replaceable": true/false, "alternatives": ["...", "..."]}}"""


def _get_cache_key(ingredient: str, recipe_name: str, ingredients: list[str]) -> str:
    """Generate a unique cache key for an ingredient-recipe combination."""
    content = f"{ingredient.lower()}|{recipe_name.lower()}|{','.join(sorted(i.lower() for i in ingredients))}"
    return hashlib.md5(content.encode()).hexdigest()


def load_replacement_cache() -> dict[str, dict]:
    """Load cached replacement checks from disk.

    Returns:
        Dict mapping cache keys to replacement results
    """
    if REPLACEMENT_CACHE_FILE.exists():
        try:
            with open(REPLACEMENT_CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def save_replacement_cache(cache: dict[str, dict]) -> None:
    """Persist replacement checks to disk.

    Args:
        cache: Dict mapping cache keys to replacement results
    """
    REPLACEMENT_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(REPLACEMENT_CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


def check_ingredient_replaceable(
    ingredient: str,
    recipe_name: str,
    all_ingredients: list[str],
    use_cache: bool = True,
) -> dict:
    """Check if an excluded ingredient can be replaced in a recipe.

    Uses GPT-4o-mini to determine if the ingredient is essential (main ingredient)
    or can be substituted (side ingredient).

    Args:
        ingredient: The ingredient to check (normalized name)
        recipe_name: Name of the recipe
        all_ingredients: List of all ingredients in the recipe
        use_cache: Whether to use cached results

    Returns:
        Dict with keys:
        - "replaceable": bool - True if ingredient can be replaced
        - "alternatives": list[str] - Suggested alternatives (empty if not replaceable)
    """
    cache_key = _get_cache_key(ingredient, recipe_name, all_ingredients)

    # Check cache first
    if use_cache:
        cache = load_replacement_cache()
        if cache_key in cache:
            return cache[cache_key]
    else:
        cache = {}

    # Call GPT
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    ingredients_list = ", ".join(all_ingredients)

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": USER_PROMPT_TEMPLATE.format(
                    ingredient=ingredient,
                    recipe_name=recipe_name,
                    ingredients_list=ingredients_list,
                )},
            ],
            temperature=0.1,
            max_tokens=200,
        )

        result_text = response.choices[0].message.content.strip()

        # Parse JSON (handle markdown code blocks)
        if result_text.startswith("```"):
            result_text = result_text.split("```")[1]
            if result_text.startswith("json"):
                result_text = result_text[4:]

        result = json.loads(result_text)

        # Ensure expected structure
        result = {
            "replaceable": bool(result.get("replaceable", False)),
            "alternatives": list(result.get("alternatives", [])),
        }

    except Exception as e:
        print(f"  Error checking replaceability for {ingredient}: {e}")
        # Default to not replaceable on error
        result = {"replaceable": False, "alternatives": []}

    # Save to cache
    cache[cache_key] = result
    save_replacement_cache(cache)

    return result


def check_excluded_ingredients_in_recipe(
    recipe_name: str,
    recipe_ingredients: list[str],
    excluded_ingredients: set[str],
) -> tuple[bool, list[str], dict[str, list[str]]]:
    """Check if a recipe is viable given excluded ingredients.

    For each excluded ingredient found in the recipe, checks if it can be replaced.

    Args:
        recipe_name: Name of the recipe
        recipe_ingredients: List of ingredients in the recipe (normalized)
        excluded_ingredients: Set of excluded ingredient names

    Returns:
        Tuple of:
        - is_viable: True if recipe can be used (no unreplaceable excluded ingredients)
        - blocking_ingredients: List of excluded ingredients that cannot be replaced
        - replacements: Dict mapping replaceable ingredients to their alternatives
    """
    blocking_ingredients = []
    replacements = {}

    # Find excluded ingredients in this recipe
    recipe_ings_lower = {ing.lower() for ing in recipe_ingredients}

    for excluded in excluded_ingredients:
        excluded_lower = excluded.lower()

        # Check if excluded ingredient is in recipe (fuzzy match)
        found_in_recipe = False
        for recipe_ing in recipe_ings_lower:
            if excluded_lower in recipe_ing or recipe_ing in excluded_lower:
                found_in_recipe = True
                break

        if not found_in_recipe:
            continue

        # Check if replaceable
        result = check_ingredient_replaceable(
            ingredient=excluded,
            recipe_name=recipe_name,
            all_ingredients=recipe_ingredients,
        )

        if result["replaceable"]:
            replacements[excluded] = result["alternatives"]
        else:
            blocking_ingredients.append(excluded)

    is_viable = len(blocking_ingredients) == 0
    return is_viable, blocking_ingredients, replacements


if __name__ == "__main__":
    # Test with example
    print("Testing ingredient replacement check...")

    test_cases = [
        {
            "ingredient": "Paprika",
            "recipe_name": "Gefüllte Paprika",
            "ingredients": ["Paprika", "Hackfleisch", "Reis", "Zwiebel", "Tomate"],
        },
        {
            "ingredient": "Paprika",
            "recipe_name": "Gemüsepfanne",
            "ingredients": ["Zucchini", "Paprika", "Zwiebel", "Knoblauch", "Olivenöl"],
        },
        {
            "ingredient": "Zwiebel",
            "recipe_name": "Spaghetti Bolognese",
            "ingredients": ["Spaghetti", "Hackfleisch", "Tomate", "Zwiebel", "Knoblauch", "Karotte"],
        },
    ]

    for tc in test_cases:
        print(f"\nRecipe: {tc['recipe_name']}")
        print(f"Checking: {tc['ingredient']}")
        result = check_ingredient_replaceable(
            ingredient=tc["ingredient"],
            recipe_name=tc["recipe_name"],
            all_ingredients=tc["ingredients"],
        )
        print(f"Result: {result}")
