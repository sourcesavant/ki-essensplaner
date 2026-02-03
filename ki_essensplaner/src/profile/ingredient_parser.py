"""Parse and normalize ingredient strings.

This module extracts structured data from ingredient strings like "200 g Tomaten"
into components: amount (200), unit (gramm), name (tomate).

Key features:
- Regex-based parsing of German and English ingredient formats
- Unit normalization (EL → esslöffel, TL → teelöffel, g → gramm)
- Basic German plural to singular conversion (Tomaten → Tomate)
- Removal of filler words and parenthetical content

Example usage:
    >>> from src.profile.ingredient_parser import parse_ingredient
    >>> parsed = parse_ingredient("200 g Kirschtomaten")
    >>> print(parsed.amount, parsed.unit, parsed.name)
    200.0 gramm kirschtomate

Issue #5: Normalisiere Bezeichnung von Zutaten und Mengen
"""

import re
from dataclasses import dataclass


@dataclass
class ParsedIngredient:
    """A parsed ingredient with structured components.

    Attributes:
        original: The original ingredient string as it appeared in the recipe
        amount: Numeric amount (e.g., 200.0 for "200 g"), None if not specified
        unit: Normalized unit (e.g., "gramm", "esslöffel"), None if not specified
        name: Normalized ingredient name in singular form
        base_ingredient: Taste-based category (filled by GPT categorization)
    """

    original: str
    amount: float | None
    unit: str | None
    name: str
    base_ingredient: str | None = None


# Mapping of unit variations to their normalized form
# Includes both German and English units for international recipe support
UNIT_MAPPING = {
    # German units
    "el": "esslöffel",
    "esslöffel": "esslöffel",
    "tl": "teelöffel",
    "teelöffel": "teelöffel",
    "g": "gramm",
    "gramm": "gramm",
    "kg": "kilogramm",
    "kilogramm": "kilogramm",
    "ml": "milliliter",
    "milliliter": "milliliter",
    "l": "liter",
    "liter": "liter",
    "stück": "stück",
    "stk": "stück",
    "prise": "prise",
    "prisen": "prise",
    "bund": "bund",
    "zehe": "zehe",
    "zehen": "zehe",
    "scheibe": "scheibe",
    "scheiben": "scheibe",
    "dose": "dose",
    "dosen": "dose",
    "becher": "becher",
    "tasse": "tasse",
    "tassen": "tasse",
    "handvoll": "handvoll",
    "msp": "messerspitze",
    "messerspitze": "messerspitze",
    "zweig": "zweig",
    "zweige": "zweig",
    "stiel": "stiel",
    "stiele": "stiel",
    "blatt": "blatt",
    "blätter": "blatt",
    # English units
    "teaspoon": "teelöffel",
    "tablespoon": "esslöffel",
    "tablespoons": "esslöffel",
    "cup": "tasse",
    "cups": "tasse",
    "clove": "zehe",
    "cloves": "zehe",
    "bunch": "bund",
    "stick": "stiel",
    "sticks": "stiel",
    "tin": "dose",
    "tins": "dose",
    "medium": "stück",
    "large": "stück",
    "small": "stück",
}


def normalize_unit(unit: str | None) -> str | None:
    """Normalize a unit string to its canonical form.

    Args:
        unit: Raw unit string (e.g., "EL", "g", "teaspoon")

    Returns:
        Normalized unit (e.g., "esslöffel", "gramm") or the original
        lowercase string if not found in mapping. Returns None if input is None.
    """
    if not unit:
        return None
    unit_lower = unit.lower().strip()
    return UNIT_MAPPING.get(unit_lower, unit_lower)


def parse_ingredient(ingredient_str: str) -> ParsedIngredient:
    """Parse an ingredient string into components.

    Examples:
        "200 g Naturreis" -> amount=200, unit="gramm", name="naturreis"
        "2 EL Olivenöl" -> amount=2, unit="esslöffel", name="olivenöl"
        "Salz" -> amount=None, unit=None, name="salz"
        "2 cloves of garlic" -> amount=2, unit="zehe", name="garlic"
    """
    original = ingredient_str.strip()
    text = original

    # Remove content in parentheses for parsing (keep for reference)
    text_clean = re.sub(r'\s*\([^)]*\)', '', text).strip()

    # Try to match: amount + unit + name
    # Pattern handles: "200 g Reis", "2 EL Öl", "1 x 400g tin of beans"

    # First, handle "X x Yunit" pattern (e.g., "1 x 400g tin")
    text_clean = re.sub(r'(\d+)\s*x\s*(\d+)', r'\2', text_clean)

    # Main pattern: number (with optional decimal) + optional unit + rest
    pattern = r'^(\d+(?:[.,]\d+)?)\s*([a-zA-ZäöüÄÖÜß]+)?\s*(.*)$'
    match = re.match(pattern, text_clean, re.IGNORECASE)

    if match:
        amount_str, unit_raw, name_raw = match.groups()

        # Parse amount
        amount = float(amount_str.replace(',', '.'))

        # Check if "unit" is actually part of the ingredient name
        # (e.g., "2 Auberginen" - "Auberginen" is not a unit)
        unit = None
        name = name_raw.strip() if name_raw else ""

        if unit_raw:
            unit_normalized = normalize_unit(unit_raw)
            if unit_normalized in UNIT_MAPPING.values():
                unit = unit_normalized
            else:
                # It's part of the name
                name = f"{unit_raw} {name}".strip()

        # If no name extracted, the "unit" might be the ingredient
        if not name and unit_raw:
            name = unit_raw
            unit = None
    else:
        # No amount found
        amount = None
        unit = None
        name = text_clean

    # Normalize name
    name = normalize_ingredient_name(name)

    return ParsedIngredient(
        original=original,
        amount=amount,
        unit=unit,
        name=name,
    )


def normalize_ingredient_name(name: str) -> str:
    """Normalize an ingredient name.

    - Lowercase
    - Remove extra whitespace
    - Basic plural -> singular (German)
    """
    if not name:
        return ""

    # Lowercase and strip
    name = name.lower().strip()

    # Remove leading punctuation and special chars
    name = re.sub(r'^[.,;:\-/½¼¾]+\s*', '', name)

    # Remove common filler words
    name = re.sub(r'\b(von|vom|der|die|das|ein|eine|einem|einer|frisch|frische|frischer|gehackt|gehackte|gehackter|gewürfelt|gewürfelte|klein|kleine|kleiner|groß|große|großer|fein|feine|feiner|grob|grobe|optional|wahlweise|etwa|ca|circa)\b', '', name)

    # Remove "of" for English ingredients
    name = re.sub(r'\bof\s+', '', name)

    # Clean up whitespace
    name = re.sub(r'\s+', ' ', name).strip()

    # Basic German plural -> singular
    # This is simplified; GPT will handle complex cases
    if name.endswith('en') and len(name) > 4:
        # Tomaten -> Tomate, Zwiebeln -> Zwiebel
        singular = name[:-1]  # Remove 'n'
        # But not for words like "Bohnen" -> "Bohne"
        name = singular if not name.endswith('nen') else name[:-1]
    elif name.endswith('n') and len(name) > 3:
        # Auberginen -> Aubergine
        pass  # Keep as is, handled above

    return name


def extract_unique_ingredient_names(ingredients: list[str]) -> list[str]:
    """Extract unique normalized ingredient names from a list."""
    names = set()
    for ing in ingredients:
        parsed = parse_ingredient(ing)
        if parsed.name:
            names.add(parsed.name)
    return sorted(names)


if __name__ == "__main__":
    # Test parsing
    test_cases = [
        "200 g Naturreis",
        "2 EL Olivenöl",
        "Salz",
        "2 Auberginen",
        "500 g Kirschtomaten",
        "200 g Linsen (z. B. Puylinsen)",
        "1 kleine Süßkartoffel (200 g)",
        "2 cloves of garlic",
        "1 heaped teaspoon chilli powder",
        "1 x 400g tin of chickpeas",
        "½ a bunch of fresh coriander (15g)",
        "Pfeffer (aus der Mühle)",
    ]

    print("Parsing tests:")
    print("=" * 60)
    for test in test_cases:
        p = parse_ingredient(test)
        print(f"{test}")
        print(f"  -> amount={p.amount}, unit={p.unit}, name={p.name}")
        print()
