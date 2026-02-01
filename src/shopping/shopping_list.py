"""Shopping list generation from weekly meal plan.

This module aggregates ingredients from selected recipes in a weekly plan
into a consolidated shopping list.

Key features:
- Groups by normalized ingredient name (NOT base_ingredient)
- Aggregates quantities with same unit
- Keeps different units separate
- Preserves specificity (Kirschtomaten ≠ Dosentomaten)

Example usage:
    >>> from src.shopping import generate_shopping_list
    >>> from src.agents import load_weekly_plan
    >>> plan = load_weekly_plan()
    >>> shopping_list = generate_shopping_list(plan)
    >>> print(shopping_list)

Issue #21: Aggregiere Zutaten aus Wochenplan für Einkaufsliste
"""

from collections import defaultdict
from dataclasses import dataclass, field

from src.agents.models import WeeklyRecommendation
from src.core.database import get_connection


@dataclass
class ShoppingItem:
    """A single item on the shopping list."""

    ingredient: str  # Normalized ingredient name
    amount: float | None = None
    unit: str | None = None
    recipes: list[str] = field(default_factory=list)  # Which recipes need this

    def __str__(self) -> str:
        if self.amount and self.unit:
            return f"{self.amount:g} {self.unit} {self.ingredient}"
        elif self.amount:
            return f"{self.amount:g} {self.ingredient}"
        else:
            return self.ingredient

    @property
    def sort_key(self) -> str:
        """Key for sorting: ingredient name."""
        return self.ingredient.lower()


@dataclass
class ShoppingList:
    """Aggregated shopping list from a weekly plan."""

    items: list[ShoppingItem] = field(default_factory=list)
    week_start: str = ""
    recipe_count: int = 0

    def __str__(self) -> str:
        lines = [f"Einkaufsliste für Woche ab {self.week_start}", ""]

        # Sort items alphabetically
        sorted_items = sorted(self.items, key=lambda x: x.sort_key)

        for item in sorted_items:
            lines.append(f"- {item}")

        lines.append("")
        lines.append(f"({len(self.items)} Positionen für {self.recipe_count} Rezepte)")
        return "\n".join(lines)

    def detailed_str(self) -> str:
        """String representation with recipe attribution."""
        lines = [f"Einkaufsliste für Woche ab {self.week_start}", ""]

        # Sort items alphabetically
        sorted_items = sorted(self.items, key=lambda x: x.sort_key)

        for item in sorted_items:
            recipe_info = f" [{', '.join(item.recipes)}]" if item.recipes else ""
            lines.append(f"- {item}{recipe_info}")

        lines.append("")
        lines.append(f"({len(self.items)} Positionen für {self.recipe_count} Rezepte)")
        return "\n".join(lines)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "week_start": self.week_start,
            "recipe_count": self.recipe_count,
            "items": [
                {
                    "ingredient": item.ingredient,
                    "amount": item.amount,
                    "unit": item.unit,
                    "recipes": item.recipes,
                }
                for item in self.items
            ],
        }


def _get_parsed_ingredients_for_recipe(recipe_id: int) -> list[dict]:
    """Get parsed ingredients for a recipe from the database.

    Args:
        recipe_id: The recipe ID

    Returns:
        List of dicts with amount, unit, ingredient, base_ingredient
    """
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT amount, unit, ingredient, base_ingredient, original
            FROM parsed_ingredients
            WHERE recipe_id = ?
            """,
            (recipe_id,),
        ).fetchall()

        return [
            {
                "amount": row["amount"],
                "unit": row["unit"],
                "ingredient": row["ingredient"],
                "base_ingredient": row["base_ingredient"],
                "original": row["original"],
            }
            for row in rows
        ]


def _normalize_unit(unit: str | None) -> str | None:
    """Normalize unit names for consistent grouping.

    Args:
        unit: Raw unit string

    Returns:
        Normalized unit or None
    """
    if not unit:
        return None

    unit = unit.lower().strip()

    # Map common variations to standard form
    unit_mapping = {
        "g": "gramm",
        "kg": "kilogramm",
        "ml": "milliliter",
        "l": "liter",
        "el": "esslöffel",
        "tl": "teelöffel",
        "essl.": "esslöffel",
        "teel.": "teelöffel",
        "msp.": "messerspitze",
        "prise": "prise",
        "stück": "stück",
        "stk": "stück",
        "bund": "bund",
        "zehe": "zehe",
        "zehen": "zehe",
        "scheibe": "scheibe",
        "scheiben": "scheibe",
    }

    return unit_mapping.get(unit, unit)


def _can_aggregate(unit1: str | None, unit2: str | None) -> bool:
    """Check if two units can be aggregated (added together).

    Args:
        unit1: First unit
        unit2: Second unit

    Returns:
        True if units are compatible for aggregation
    """
    norm1 = _normalize_unit(unit1)
    norm2 = _normalize_unit(unit2)

    # Both None or both same = can aggregate
    if norm1 == norm2:
        return True

    return False


def generate_shopping_list(plan: WeeklyRecommendation) -> ShoppingList:
    """Generate a shopping list from a weekly meal plan.

    Aggregates ingredients from all selected recipes, grouping by
    normalized ingredient name and unit.

    Args:
        plan: Weekly meal plan with selected recipes

    Returns:
        ShoppingList with aggregated items
    """
    # Collect all ingredients: {(ingredient, unit): {"amount": float, "recipes": [...]}}
    aggregated: dict[tuple[str, str | None], dict] = defaultdict(
        lambda: {"amount": 0.0, "recipes": [], "has_amount": False}
    )

    recipe_count = 0
    selected_recipes = plan.get_selected_recipes()

    for weekday, slot, recipe in selected_recipes:
        recipe_label = f"{weekday} {slot}"

        # Get ingredients - prefer from DB if recipe_id exists
        if recipe.recipe_id:
            parsed = _get_parsed_ingredients_for_recipe(recipe.recipe_id)
            recipe_count += 1

            for ing in parsed:
                ingredient = ing["ingredient"]
                unit = _normalize_unit(ing["unit"])
                amount = ing["amount"]

                key = (ingredient, unit)

                if amount:
                    aggregated[key]["amount"] += amount
                    aggregated[key]["has_amount"] = True

                if recipe_label not in aggregated[key]["recipes"]:
                    aggregated[key]["recipes"].append(recipe_label)

        elif recipe.ingredients:
            # Fallback: use raw ingredients from recipe (for new recipes without DB entry)
            recipe_count += 1

            for ing_str in recipe.ingredients:
                # Simple parsing: just use the ingredient string as-is
                key = (ing_str.lower(), None)
                aggregated[key]["has_amount"] = False

                if recipe_label not in aggregated[key]["recipes"]:
                    aggregated[key]["recipes"].append(recipe_label)

    # Convert to ShoppingItems
    items = []
    for (ingredient, unit), data in aggregated.items():
        amount = data["amount"] if data["has_amount"] else None
        items.append(
            ShoppingItem(
                ingredient=ingredient,
                amount=amount,
                unit=unit,
                recipes=data["recipes"],
            )
        )

    return ShoppingList(
        items=items,
        week_start=plan.week_start,
        recipe_count=recipe_count,
    )


if __name__ == "__main__":
    from src.agents.models import load_weekly_plan

    print("=" * 60)
    print("Shopping List Generator Test")
    print("=" * 60)

    # Load the saved weekly plan
    plan = load_weekly_plan()

    if not plan:
        print("No weekly plan found. Run the search agent first.")
        exit(1)

    print(f"Loaded plan for week: {plan.week_start}")
    print(f"Selected recipes: {len(plan.get_selected_recipes())}")
    print()

    # Generate shopping list
    shopping_list = generate_shopping_list(plan)

    print(shopping_list)
