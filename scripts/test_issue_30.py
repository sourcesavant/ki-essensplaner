"""Test script for Issue #30: Portionenanzahl & Rezept-Skalierung."""

from src.core.user_config import get_household_size, set_household_size, load_config


def test_config():
    """Test configuration system."""
    print("Testing configuration system...")

    # Test get household size (default)
    size = get_household_size()
    print(f"  Default household size: {size}")

    # Test set household size
    set_household_size(4)
    print(f"  Set household size to 4")

    # Test get household size (after set)
    size = get_household_size()
    print(f"  New household size: {size}")
    assert size == 4, "Household size should be 4"

    # Test load config
    config = load_config()
    print(f"  Config: {config}")
    assert config.get("household_size") == 4
    assert "updated_at" in config

    # Test validation
    try:
        set_household_size(11)  # Should fail
        assert False, "Should have raised ValueError"
    except ValueError as e:
        print(f"  Validation works: {e}")

    # Reset to default
    set_household_size(2)
    print(f"  Reset to default (2)")

    print("[OK] Configuration system test passed!\n")


def test_servings_in_recipes():
    """Test that servings field is available in recipes."""
    print("Testing servings in recipes...")

    from src.core.database import get_all_recipes

    recipes = get_all_recipes()
    if not recipes:
        print("  No recipes in database, skipping test")
        return

    recipe = recipes[0]
    print(f"  Sample recipe: {recipe.title}")
    print(f"  Servings: {recipe.servings}")

    # Check that servings attribute exists (even if None)
    assert hasattr(recipe, "servings"), "Recipe should have servings attribute"

    print("[OK] Servings field test passed!\n")


def test_scaling():
    """Test scaling logic."""
    print("Testing scaling logic...")

    from src.shopping.shopping_list import round_amount

    # Test rounding
    tests = [
        (167, "gramm", 170),
        (1.7, "stück", 2),
        (0.75, "esslöffel", 1.0),
        (23.4, "gramm", 20),
        (2.3, "teelöffel", 2.5),
    ]

    for amount, unit, expected in tests:
        result = round_amount(amount, unit)
        print(f"  round_amount({amount}, '{unit}') = {result} (expected: {expected})")
        assert result == expected, f"Expected {expected}, got {result}"

    print("[OK] Scaling logic test passed!\n")


if __name__ == "__main__":
    print("=" * 60)
    print("Issue #30 Test Suite")
    print("=" * 60)
    print()

    test_config()
    test_servings_in_recipes()
    test_scaling()

    print("=" * 60)
    print("All tests passed!")
    print("=" * 60)
