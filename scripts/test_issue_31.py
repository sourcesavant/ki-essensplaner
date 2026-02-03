"""Test suite for Issue #31: Multi-Day Meal Prep (Vorkochen).

This tests the complete multi-day meal prep functionality including:
- Model changes (MultiDayGroup, SlotRecommendation)
- WeeklyRecommendation multi-day methods
- Shopping list quantity multiplication
- JSON serialization/deserialization
"""

from src.agents.models import (
    MultiDayGroup,
    ScoredRecipe,
    SlotRecommendation,
    WeeklyRecommendation,
)
from src.shopping.shopping_list import generate_shopping_list


def test_multi_day_group():
    """Test MultiDayGroup class."""
    print("Test 1: MultiDayGroup")
    print("-" * 40)

    group = MultiDayGroup(
        primary_weekday="Sonntag",
        primary_slot="Abendessen",
        reuse_slots=[("Montag", "Abendessen"), ("Dienstag", "Abendessen")],
    )

    assert group.total_days == 3, f"Expected 3 days, got {group.total_days}"
    assert group.multiplier == 3.0, f"Expected multiplier 3.0, got {group.multiplier}"

    print(f"  Primary: {group.primary_weekday} {group.primary_slot}")
    print(f"  Reuse slots: {group.reuse_slots}")
    print(f"  Total days: {group.total_days}")
    print(f"  Multiplier: {group.multiplier}")
    print("[OK] MultiDayGroup test passed!\n")


def test_slot_recommendation():
    """Test SlotRecommendation with multi-day fields."""
    print("Test 2: SlotRecommendation")
    print("-" * 40)

    recipe = ScoredRecipe(
        title="Lasagne",
        url="https://example.com/lasagne",
        score=85.0,
        reasoning="Great for meal prep",
        is_new=False,
        recipe_id=1,
        servings=4,
    )

    # Normal slot with multi-day prep
    slot = SlotRecommendation(
        weekday="Sonntag",
        slot="Abendessen",
        recommendations=[recipe],
        prep_days=3,
    )

    assert not slot.is_reuse_slot, "Should not be a reuse slot"
    assert slot.prep_days == 3, "prep_days should be 3"
    print(f"  Normal slot with prep_days=3: {slot.weekday} {slot.slot}")

    # Reuse slot
    reuse_slot = SlotRecommendation(
        weekday="Montag",
        slot="Abendessen",
        recommendations=[],
        reuse_from=("Sonntag", "Abendessen"),
    )

    assert reuse_slot.is_reuse_slot, "Should be a reuse slot"
    assert reuse_slot.selected_recipe is None, "Reuse slot should have no recipe"
    print(f"  Reuse slot: {reuse_slot.weekday} {reuse_slot.slot}")
    print(f"  Reuses from: {reuse_slot.reuse_from}")

    print("[OK] SlotRecommendation test passed!\n")


def test_weekly_recommendation_multi_day():
    """Test WeeklyRecommendation multi-day methods."""
    print("Test 3: WeeklyRecommendation multi-day methods")
    print("-" * 40)

    recipe = ScoredRecipe(
        title="Chili con Carne",
        url="https://example.com/chili",
        score=90.0,
        reasoning="Perfect for batch cooking",
        is_new=False,
        recipe_id=2,
        servings=4,
    )

    plan = WeeklyRecommendation(
        slots=[
            SlotRecommendation(
                weekday="Sonntag", slot="Abendessen", recommendations=[recipe]
            ),
            SlotRecommendation(
                weekday="Montag", slot="Abendessen", recommendations=[recipe]
            ),
            SlotRecommendation(
                weekday="Dienstag", slot="Abendessen", recommendations=[recipe]
            ),
        ]
    )

    # Set multi-day
    result = plan.set_multi_day(
        "Sonntag",
        "Abendessen",
        [("Montag", "Abendessen"), ("Dienstag", "Abendessen")],
    )

    assert result is True, "set_multi_day should return True"
    assert len(plan.multi_day_groups) == 1, "Should have 1 multi-day group"

    # Check primary slot
    sunday = plan.get_slot("Sonntag", "Abendessen")
    assert sunday is not None
    assert sunday.prep_days == 3, f"Expected prep_days=3, got {sunday.prep_days}"
    print(f"  Primary slot prep_days: {sunday.prep_days}")

    # Check reuse slots
    monday = plan.get_slot("Montag", "Abendessen")
    assert monday is not None
    assert monday.is_reuse_slot, "Monday should be a reuse slot"
    assert monday.reuse_from == ("Sonntag", "Abendessen")
    print(f"  Monday is_reuse_slot: {monday.is_reuse_slot}")

    tuesday = plan.get_slot("Dienstag", "Abendessen")
    assert tuesday is not None
    assert tuesday.is_reuse_slot, "Tuesday should be a reuse slot"
    print(f"  Tuesday is_reuse_slot: {tuesday.is_reuse_slot}")

    # Check get_recipe_for_slot (should return recipe from primary)
    recipe_for_monday = plan.get_recipe_for_slot("Montag", "Abendessen")
    assert recipe_for_monday is not None, "Should get recipe from primary slot"
    assert recipe_for_monday.title == "Chili con Carne"
    print(f"  Recipe for Monday: {recipe_for_monday.title}")

    # Test clear_multi_day
    result = plan.clear_multi_day("Montag", "Abendessen")
    assert result is True, "clear_multi_day should return True"
    assert monday.reuse_from is None, "Monday should no longer be a reuse slot"
    print(f"  After clear: Monday is_reuse_slot: {monday.is_reuse_slot}")

    print("[OK] WeeklyRecommendation multi-day test passed!\n")


def test_json_serialization():
    """Test JSON serialization with multi-day groups."""
    print("Test 4: JSON serialization with multi-day")
    print("-" * 40)

    recipe = ScoredRecipe(
        title="Lasagne",
        url="https://example.com/lasagne",
        score=85.0,
        reasoning="Test",
        is_new=False,
        recipe_id=1,
        servings=6,
    )

    plan = WeeklyRecommendation(
        slots=[
            SlotRecommendation(
                weekday="Sonntag", slot="Abendessen", recommendations=[recipe]
            ),
            SlotRecommendation(
                weekday="Montag", slot="Abendessen", recommendations=[recipe]
            ),
        ]
    )

    plan.set_multi_day("Sonntag", "Abendessen", [("Montag", "Abendessen")])

    # Test to_dict
    data = plan.to_dict()
    assert "multi_day_groups" in data
    assert len(data["multi_day_groups"]) == 1
    assert data["multi_day_groups"][0]["primary_weekday"] == "Sonntag"
    print(f"  Serialized multi_day_groups: {len(data['multi_day_groups'])}")

    # Test from_dict
    restored_plan = WeeklyRecommendation.from_dict(data)
    assert len(restored_plan.multi_day_groups) == 1
    assert restored_plan.multi_day_groups[0].primary_weekday == "Sonntag"

    sunday = restored_plan.get_slot("Sonntag", "Abendessen")
    assert sunday.prep_days == 2
    print(f"  Restored prep_days: {sunday.prep_days}")

    monday = restored_plan.get_slot("Montag", "Abendessen")
    assert monday.is_reuse_slot
    print(f"  Restored is_reuse_slot: {monday.is_reuse_slot}")

    print("[OK] JSON serialization test passed!\n")


def test_shopping_list_scaling():
    """Test shopping list with multi-day scaling."""
    print("Test 5: Shopping list multi-day scaling")
    print("-" * 40)

    # Create a plan with multi-day meal prep
    lasagne = ScoredRecipe(
        title="Lasagne",
        url="https://bioland-huesgen.de/rezepte/lasagne",
        score=85.0,
        reasoning="Great for batch cooking",
        is_new=False,
        recipe_id=1,  # Must exist in DB for ingredient parsing
        servings=4,
    )

    plan = WeeklyRecommendation(
        week_start="2026-02-03",
        slots=[
            SlotRecommendation(
                weekday="Sonntag",
                slot="Abendessen",
                recommendations=[lasagne],
                selected_index=0,
            ),
            SlotRecommendation(
                weekday="Montag",
                slot="Abendessen",
                recommendations=[],
            ),
            SlotRecommendation(
                weekday="Dienstag",
                slot="Abendessen",
                recommendations=[],
            ),
        ],
    )

    # Configure multi-day: Cook on Sunday, eat on Sunday + Monday + Tuesday
    plan.set_multi_day(
        "Sonntag",
        "Abendessen",
        [("Montag", "Abendessen"), ("Dienstag", "Abendessen")],
    )

    # Generate shopping list with household_size=2
    shopping_list = generate_shopping_list(plan, household_size=2)

    print(f"  Week start: {shopping_list.week_start}")
    print(f"  Household size: {shopping_list.household_size}")
    print(f"  Recipe count: {shopping_list.recipe_count}")
    print(f"  Items: {len(shopping_list.items)}")

    # Check multi-day info
    assert len(shopping_list.multi_day_info) == 1, "Should have 1 multi-day entry"
    multi_day = shopping_list.multi_day_info[0]
    print(f"\n  Multi-day info:")
    print(f"    Recipe: {multi_day['recipe']}")
    print(f"    Cook on: {multi_day['cook_on']}")
    print(f"    Eat on: {multi_day['eat_on']}")
    print(f"    Total days: {multi_day['total_days']}")
    print(f"    Multiplier: {multi_day['multiplier']}")

    assert multi_day["total_days"] == 3
    assert multi_day["multiplier"] == 3.0

    # Check scale info
    if shopping_list.scale_info:
        print(f"\n  Scale info:")
        for info in shopping_list.scale_info:
            print(f"    {info['recipe']}: {info['original_servings']} -> {info['scaled_to']} x {info['prep_days']} days = {info['factor']}x")

    # Verify Sunday slot
    sunday = plan.get_slot("Sonntag", "Abendessen")
    assert sunday.prep_days == 3, "Sunday should prep for 3 days"

    # Verify reuse slots
    monday = plan.get_slot("Montag", "Abendessen")
    assert monday.is_reuse_slot, "Monday should be reuse slot"

    tuesday = plan.get_slot("Dienstag", "Abendessen")
    assert tuesday.is_reuse_slot, "Tuesday should be reuse slot"

    print("\n[OK] Shopping list multi-day scaling test passed!\n")


def test_shopping_list_to_dict():
    """Test shopping list to_dict with multi-day info."""
    print("Test 6: Shopping list to_dict with multi-day")
    print("-" * 40)

    recipe = ScoredRecipe(
        title="Gulasch",
        url="https://example.com/gulasch",
        score=88.0,
        reasoning="Perfect for batch cooking",
        is_new=False,
        recipe_id=3,
        servings=6,
    )

    plan = WeeklyRecommendation(
        week_start="2026-02-10",
        slots=[
            SlotRecommendation(
                weekday="Samstag",
                slot="Mittagessen",
                recommendations=[recipe],
                selected_index=0,
            ),
            SlotRecommendation(
                weekday="Sonntag",
                slot="Mittagessen",
                recommendations=[],
            ),
        ],
    )

    plan.set_multi_day("Samstag", "Mittagessen", [("Sonntag", "Mittagessen")])

    shopping_list = generate_shopping_list(plan, household_size=4)
    data = shopping_list.to_dict()

    assert "multi_day_info" in data
    assert len(data["multi_day_info"]) == 1
    assert data["household_size"] == 4
    print(f"  Household size in dict: {data['household_size']}")
    print(f"  Multi-day info entries: {len(data['multi_day_info'])}")

    print("[OK] Shopping list to_dict test passed!\n")


if __name__ == "__main__":
    print("=" * 60)
    print("Issue #31: Multi-Day Meal Prep - Test Suite")
    print("=" * 60)
    print()

    try:
        test_multi_day_group()
        test_slot_recommendation()
        test_weekly_recommendation_multi_day()
        test_json_serialization()
        test_shopping_list_scaling()
        test_shopping_list_to_dict()

        print("=" * 60)
        print("All tests passed!")
        print("=" * 60)

    except AssertionError as e:
        print(f"\n[ERROR] Test failed: {e}")
        exit(1)
    except Exception as e:
        print(f"\n[ERROR] Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
