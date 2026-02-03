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
from src.core.database import (
    get_available_base_ingredients,
    get_connection,
    get_ingredient_synonyms,
)


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
    household_size: int = 2
    scale_info: list[dict] = field(default_factory=list)
    multi_day_info: list[dict] = field(default_factory=list)

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

    def split_by_store(self) -> "SplitShoppingList":
        """Split the shopping list by store (Bioland vs Rewe).

        Items available at Bioland Hüsgen go to the Bioland list,
        everything else goes to Rewe.

        Returns:
            SplitShoppingList with bioland and rewe lists
        """
        return split_shopping_list_by_store(self)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "week_start": self.week_start,
            "recipe_count": self.recipe_count,
            "household_size": self.household_size,
            "scale_info": self.scale_info,
            "multi_day_info": self.multi_day_info,
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


@dataclass
class SplitShoppingList:
    """Shopping list split by store."""

    bioland: list[ShoppingItem] = field(default_factory=list)
    rewe: list[ShoppingItem] = field(default_factory=list)
    week_start: str = ""
    household_size: int = 2

    def __str__(self) -> str:
        lines = [f"Einkaufslisten für Woche ab {self.week_start}", ""]

        # Bioland list
        lines.append("=" * 40)
        lines.append("BIOLAND HÜSGEN")
        lines.append("=" * 40)
        if self.bioland:
            for item in sorted(self.bioland, key=lambda x: x.sort_key):
                lines.append(f"- {item}")
        else:
            lines.append("(keine Artikel)")
        lines.append(f"\n({len(self.bioland)} Positionen)")

        lines.append("")

        # Rewe list
        lines.append("=" * 40)
        lines.append("REWE")
        lines.append("=" * 40)
        if self.rewe:
            for item in sorted(self.rewe, key=lambda x: x.sort_key):
                lines.append(f"- {item}")
        else:
            lines.append("(keine Artikel)")
        lines.append(f"\n({len(self.rewe)} Positionen)")

        return "\n".join(lines)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "week_start": self.week_start,
            "household_size": self.household_size,
            "bioland": [
                {
                    "ingredient": item.ingredient,
                    "amount": item.amount,
                    "unit": item.unit,
                    "recipes": item.recipes,
                }
                for item in self.bioland
            ],
            "rewe": [
                {
                    "ingredient": item.ingredient,
                    "amount": item.amount,
                    "unit": item.unit,
                    "recipes": item.recipes,
                }
                for item in self.rewe
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


def _is_available_at_bioland(ingredient: str, available: set[str]) -> bool:
    """Check if an ingredient is available at Bioland.

    Args:
        ingredient: Normalized ingredient name
        available: Set of available base ingredients at Bioland

    Returns:
        True if available at Bioland
    """
    ingredient_lower = ingredient.lower()

    # Direct match
    if ingredient_lower in available:
        return True

    # Check synonyms
    synonyms = get_ingredient_synonyms(ingredient_lower)
    if synonyms & available:
        return True

    # Fuzzy match: check if ingredient is contained in any available item or vice versa
    for avail in available:
        if ingredient_lower in avail or avail in ingredient_lower:
            return True

    return False


def round_amount(amount: float, unit: str | None) -> float:
    """Round amount to sensible values based on unit.

    Args:
        amount: The amount to round
        unit: The unit (normalized)

    Returns:
        Rounded amount
    """
    if unit in ("gramm", "milliliter"):
        # Round to nearest 10 (e.g., 167g -> 170g)
        return round(amount / 10) * 10
    elif unit in ("stück", "scheibe"):
        # Round to whole numbers, minimum 1
        return max(1, round(amount))
    elif unit in ("esslöffel", "teelöffel"):
        # Round to nearest 0.5
        return round(amount * 2) / 2
    else:
        # Default: round to 1 decimal place
        return round(amount, 1)


def split_shopping_list_by_store(shopping_list: ShoppingList) -> SplitShoppingList:
    """Split a shopping list into Bioland and Rewe lists.

    Items available at Bioland Hüsgen go to the Bioland list,
    everything else goes to Rewe.

    Args:
        shopping_list: The aggregated shopping list

    Returns:
        SplitShoppingList with bioland and rewe lists
    """
    # Get available ingredients at Bioland
    available = get_available_base_ingredients("bioland_huesgen")
    available_lower = {ing.lower() for ing in available}

    bioland_items = []
    rewe_items = []

    for item in shopping_list.items:
        if _is_available_at_bioland(item.ingredient, available_lower):
            bioland_items.append(item)
        else:
            rewe_items.append(item)

    return SplitShoppingList(
        bioland=bioland_items,
        rewe=rewe_items,
        week_start=shopping_list.week_start,
        household_size=shopping_list.household_size,
    )


def generate_shopping_list(
    plan: WeeklyRecommendation,
    household_size: int | None = None,
) -> ShoppingList:
    """Generate a shopping list from a weekly meal plan.

    Aggregates ingredients from all selected recipes, grouping by
    normalized ingredient name and unit. Automatically scales quantities
    based on household size and multi-day meal prep.

    Args:
        plan: Weekly meal plan with selected recipes
        household_size: Number of people (1-10). If None, loads from config.

    Returns:
        ShoppingList with aggregated and scaled items
    """
    from src.core.user_config import get_household_size

    if household_size is None:
        household_size = get_household_size()

    # Collect all ingredients: {(ingredient, unit): {"amount": float, "recipes": [...]}}
    aggregated: dict[tuple[str, str | None], dict] = defaultdict(
        lambda: {"amount": 0.0, "recipes": [], "has_amount": False}
    )

    recipe_count = 0
    scale_info: list[dict] = []

    # Process each slot
    for slot_rec in plan.slots:
        # Skip reuse slots (quantities come from primary slot)
        if slot_rec.is_reuse_slot:
            continue

        recipe = slot_rec.selected_recipe
        if not recipe:
            continue

        # Calculate scaling factors
        recipe_servings = recipe.servings or 2  # Default: 2 servings
        household_factor = household_size / recipe_servings

        # Multi-day factor
        prep_days_factor = slot_rec.prep_days  # 1, 2, 3, ...
        total_factor = household_factor * prep_days_factor

        # Recipe label for attribution
        if slot_rec.prep_days > 1:
            # List all days this recipe is used
            source_days = [f"{slot_rec.weekday} {slot_rec.slot}"]
            for group in plan.multi_day_groups:
                if group.primary_weekday == slot_rec.weekday and group.primary_slot == slot_rec.slot:
                    source_days.extend([f"{w} {s}" for w, s in group.reuse_slots])
            recipe_label = " + ".join(source_days)
        else:
            recipe_label = f"{slot_rec.weekday} {slot_rec.slot}"

        # Track scaling info for transparency
        if recipe_servings != household_size or prep_days_factor > 1:
            scale_info.append({
                "slot": recipe_label,
                "recipe": recipe.title,
                "original_servings": recipe_servings,
                "scaled_to": household_size,
                "prep_days": prep_days_factor,
                "factor": round(total_factor, 2),
            })

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
                    # Scale the amount
                    scaled_amount = amount * total_factor
                    aggregated[key]["amount"] += scaled_amount
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

    # Convert to ShoppingItems with rounded amounts
    items = []
    for (ingredient, unit), data in aggregated.items():
        if data["has_amount"]:
            # Round to sensible values
            amount = round_amount(data["amount"], unit)
        else:
            amount = None

        items.append(
            ShoppingItem(
                ingredient=ingredient,
                amount=amount,
                unit=unit,
                recipes=data["recipes"],
            )
        )

    # Multi-day info for transparency
    multi_day_info = []
    for group in plan.multi_day_groups:
        recipe = plan.get_recipe_for_slot(group.primary_weekday, group.primary_slot)
        if recipe:
            multi_day_info.append({
                "recipe": recipe.title,
                "cook_on": f"{group.primary_weekday} {group.primary_slot}",
                "eat_on": [
                    f"{group.primary_weekday} {group.primary_slot}"
                ] + [f"{w} {s}" for w, s in group.reuse_slots],
                "total_days": group.total_days,
                "multiplier": group.multiplier,
            })

    return ShoppingList(
        items=items,
        week_start=plan.week_start,
        recipe_count=recipe_count,
        household_size=household_size,
        scale_info=scale_info,
        multi_day_info=multi_day_info,
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
