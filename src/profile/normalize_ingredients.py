"""Normalize and store all recipe ingredients in the database.

This module processes all recipes and stores their parsed/normalized
ingredients in the parsed_ingredients table. This enables:
- Ingredient frequency analysis for preference profiling
- Aggregation of shopping lists
- Recipe similarity calculations

The normalization pipeline:
1. Parse ingredient strings (amount, unit, name)
2. Look up taste-based categorization from GPT cache
3. Store normalized data in parsed_ingredients table

Example usage:
    >>> from src.profile.normalize_ingredients import normalize_all_recipes
    >>> stats = normalize_all_recipes()
    >>> print(f"Processed {stats['ingredients']} ingredients")

    >>> from src.profile.normalize_ingredients import get_ingredient_frequencies
    >>> top = get_ingredient_frequencies()[:5]
    >>> for item in top:
    ...     print(f"{item['base_ingredient']}: {item['recipe_count']} recipes")

Issue #5: Normalisiere Bezeichnung von Zutaten und Mengen
"""

from src.core.database import get_all_recipes, get_connection
from src.profile.ingredient_parser import parse_ingredient
from src.profile.ingredient_categorizer import load_cache, categorize_ingredients_batch


def create_parsed_ingredients_table() -> None:
    """Create the parsed_ingredients table if it doesn't exist."""
    with get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS parsed_ingredients (
                id INTEGER PRIMARY KEY,
                recipe_id INTEGER REFERENCES recipes(id),
                original TEXT,
                amount REAL,
                unit TEXT,
                ingredient TEXT,
                base_ingredient TEXT
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_parsed_ingredients_recipe
            ON parsed_ingredients(recipe_id)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_parsed_ingredients_base
            ON parsed_ingredients(base_ingredient)
        """)


def clear_parsed_ingredients() -> None:
    """Clear all parsed ingredients."""
    with get_connection() as conn:
        conn.execute("DELETE FROM parsed_ingredients")


def normalize_all_recipes() -> dict:
    """Parse and normalize all ingredients for all recipes.

    Returns:
        Stats dict with counts
    """
    # Ensure table exists
    create_parsed_ingredients_table()

    # Clear existing data
    clear_parsed_ingredients()

    # Load categorization cache
    cache = load_cache()

    # Get all recipes
    recipes = [r for r in get_all_recipes() if r.source != "test"]

    stats = {"recipes": 0, "ingredients": 0, "categorized": 0}

    print(f"Normalizing ingredients for {len(recipes)} recipes...")

    with get_connection() as conn:
        for recipe in recipes:
            for ing_str in recipe.ingredients:
                # Parse the ingredient
                parsed = parse_ingredient(ing_str)

                # Get categorization
                name_normalized = parsed.name
                base_ingredient = parsed.name

                if parsed.name in cache:
                    cat = cache[parsed.name]
                    name_normalized = cat.get("name_normalized", parsed.name)
                    base_ingredient = cat.get("base_ingredient", name_normalized)
                    stats["categorized"] += 1

                # Insert into database
                conn.execute(
                    """
                    INSERT INTO parsed_ingredients
                    (recipe_id, original, amount, unit, ingredient, base_ingredient)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        recipe.id,
                        parsed.original,
                        parsed.amount,
                        parsed.unit,
                        name_normalized,
                        base_ingredient,
                    ),
                )
                stats["ingredients"] += 1

            stats["recipes"] += 1

    print(f"Done! Processed {stats['recipes']} recipes, "
          f"{stats['ingredients']} ingredients, "
          f"{stats['categorized']} categorized.")

    return stats


def get_ingredient_frequencies() -> list[dict]:
    """Get base ingredient frequencies across all recipes.

    Returns:
        List of {base_ingredient, count, recipe_count} sorted by count
    """
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT
                base_ingredient,
                COUNT(*) as total_count,
                COUNT(DISTINCT recipe_id) as recipe_count
            FROM parsed_ingredients
            WHERE base_ingredient IS NOT NULL AND base_ingredient != ''
            GROUP BY base_ingredient
            ORDER BY recipe_count DESC, total_count DESC
        """).fetchall()

    return [
        {
            "base_ingredient": row["base_ingredient"],
            "total_count": row["total_count"],
            "recipe_count": row["recipe_count"],
        }
        for row in rows
    ]


def get_recipe_ingredients(recipe_id: int) -> list[dict]:
    """Get parsed ingredients for a recipe.

    Returns:
        List of {original, amount, unit, ingredient, base_ingredient}
    """
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT original, amount, unit, ingredient, base_ingredient
            FROM parsed_ingredients
            WHERE recipe_id = ?
            ORDER BY id
            """,
            (recipe_id,),
        ).fetchall()

    return [dict(row) for row in rows]


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()

    # First, ensure all ingredients are categorized
    from src.profile.ingredient_parser import parse_ingredient

    recipes = [r for r in get_all_recipes() if r.source != "test"]
    names = set()
    for r in recipes:
        for ing in r.ingredients:
            parsed = parse_ingredient(ing)
            if parsed.name and len(parsed.name) > 1:
                names.add(parsed.name)

    print(f"Ensuring {len(names)} ingredients are categorized...")
    categorize_ingredients_batch(list(names), batch_size=50)

    # Then normalize all
    print()
    normalize_all_recipes()

    # Show top ingredients
    print()
    print("Top 20 Basis-Zutaten:")
    print("=" * 50)
    freqs = get_ingredient_frequencies()
    for i, f in enumerate(freqs[:20], 1):
        print(f"{i:2}. {f['base_ingredient']:25} ({f['recipe_count']} Rezepte, {f['total_count']}x)")
