"""Categorize ingredients using GPT-4o-mini.

Issue #5: Normalisiere Bezeichnung von Zutaten und Mengen
"""

import json
import os
from pathlib import Path

from openai import OpenAI

from src.core.config import DATA_DIR

# Cache file for categorizations
CACHE_FILE = DATA_DIR / "local" / "ingredient_categories.json"

SYSTEM_PROMPT = """Du bist ein Experte für Lebensmittel und Geschmacksprofile.

Deine Aufgabe ist es, Zutaten zu kategorisieren nach:
1. **name_normalized**: Deutscher Name, Singular, kleingeschrieben (z.B. "tomate", "zwiebel")
2. **base_ingredient**: Geschmackskategorie - SPEZIFISCH, nicht generisch!

WICHTIG für base_ingredient:
- Verwende SPEZIFISCHE Namen, NICHT generische wie "gewürz", "gemüse", "neutral", "frucht"
- base_ingredient = name_normalized in den meisten Fällen
- NUR zusammenfassen wenn der GESCHMACK wirklich gleich ist:

Beispiele für Zusammenfassung (gleicher Geschmack):
- kirschtomate, dosentomate, strauchtomate → tomate
- rote zwiebel, weiße zwiebel, schalotte → zwiebel
- parmesan, grana padano, pecorino → hartkäse_würzig
- gouda, emmentaler, bergkäse → schnittkäse
- sonnenblumenöl, rapsöl, pflanzenöl → neutrales_öl

Beispiele für GETRENNT halten (unterschiedlicher Geschmack):
- salz → salz (NICHT "gewürz")
- pfeffer → pfeffer (NICHT "gewürz")
- ingwer → ingwer (NICHT "gewürz")
- knoblauch → knoblauch (NICHT "gewürz")
- kreuzkümmel → kreuzkümmel
- paprika → paprika
- kartoffel → kartoffel (NICHT "neutral" oder "gemüse")
- karotte → karotte
- brokkoli → brokkoli
- butter → butter
- nudel → nudel
- reis → reis
- olivenöl → olivenöl (eigener Geschmack, NICHT "öl")
- zitrone → zitrone
- limette → limette
- apfel → apfel
- feta → feta
- mozzarella → mozzarella
- hähnchen → hähnchen
- hackfleisch → hackfleisch

Antworte NUR mit einem JSON-Array, keine Erklärungen."""

USER_PROMPT_TEMPLATE = """Kategorisiere diese Zutaten:

{ingredients}

Antworte mit einem JSON-Array:
[
  {{"original": "...", "name_normalized": "...", "base_ingredient": "..."}},
  ...
]"""


def load_cache() -> dict[str, dict]:
    """Load cached categorizations."""
    if CACHE_FILE.exists():
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_cache(cache: dict[str, dict]) -> None:
    """Save categorizations to cache."""
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


def categorize_ingredients_batch(
    ingredients: list[str],
    batch_size: int = 50,
) -> dict[str, dict]:
    """Categorize ingredients using GPT-4o-mini.

    Args:
        ingredients: List of ingredient names to categorize
        batch_size: Number of ingredients per API call

    Returns:
        Dict mapping original ingredient to {name_normalized, base_ingredient}
    """
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    # Load cache
    cache = load_cache()

    # Filter out already cached
    to_categorize = [ing for ing in ingredients if ing not in cache]

    if not to_categorize:
        print("All ingredients already cached.")
        return cache

    print(f"Categorizing {len(to_categorize)} ingredients ({len(cache)} cached)...")

    # Process in batches
    for i in range(0, len(to_categorize), batch_size):
        batch = to_categorize[i:i + batch_size]
        print(f"  Batch {i // batch_size + 1}: {len(batch)} ingredients...")

        # Format ingredients for prompt
        ing_list = "\n".join(f"- {ing}" for ing in batch)

        try:
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": USER_PROMPT_TEMPLATE.format(ingredients=ing_list)},
                ],
                temperature=0.1,
                max_tokens=4000,
            )

            result_text = response.choices[0].message.content.strip()

            # Parse JSON (handle markdown code blocks)
            if result_text.startswith("```"):
                result_text = result_text.split("```")[1]
                if result_text.startswith("json"):
                    result_text = result_text[4:]

            results = json.loads(result_text)

            # Add to cache
            for item in results:
                original = item.get("original", "")
                if original:
                    cache[original] = {
                        "name_normalized": item.get("name_normalized", original),
                        "base_ingredient": item.get("base_ingredient", item.get("name_normalized", original)),
                    }

        except Exception as e:
            print(f"  Error in batch: {e}")
            # Add uncategorized items to cache with original name
            for ing in batch:
                if ing not in cache:
                    cache[ing] = {
                        "name_normalized": ing,
                        "base_ingredient": ing,
                    }

    # Save cache
    save_cache(cache)
    print(f"Saved {len(cache)} categorizations to cache.")

    return cache


def get_base_ingredient(ingredient_name: str, cache: dict[str, dict] | None = None) -> str:
    """Get the base ingredient category for an ingredient name."""
    if cache is None:
        cache = load_cache()

    if ingredient_name in cache:
        return cache[ingredient_name].get("base_ingredient", ingredient_name)

    return ingredient_name


if __name__ == "__main__":
    # Test with a few ingredients
    test_ingredients = [
        "kirschtomate",
        "dosentomate",
        "feta",
        "parmesan",
        "mozzarella",
        "olivenöl",
        "sonnenblumenöl",
        "rote zwiebel",
        "frühlingszwiebel",
        "garlic",
        "red peppers",
        "fresh coriander",
    ]

    print("Testing ingredient categorization...")
    results = categorize_ingredients_batch(test_ingredients)

    print("\nResults:")
    for ing in test_ingredients:
        if ing in results:
            r = results[ing]
            print(f"  {ing} -> {r['name_normalized']} ({r['base_ingredient']})")
