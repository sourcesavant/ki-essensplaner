"""Work-in-Progress test for Issue #31: Multi-Day Meal Prep.

This tests the model changes and basic functionality.
"""

from src.agents.models import (
    MultiDayGroup,
    ScoredRecipe,
    SlotRecommendation,
    WeeklyRecommendation,
)


def test_multi_day_group():
    """Test MultiDayGroup class."""
    print("Testing MultiDayGroup...")

    group = MultiDayGroup(
        primary_weekday="Sonntag",
        primary_slot="Abendessen",
        reuse_slots=[("Montag", "Abendessen"), ("Dienstag", "Abendessen")],
    )

    assert group.total_days == 3, f"Expected 3 days, got {group.total_days}"
    assert group.multiplier == 3.0, f"Expected multiplier 3.0, got {group.multiplier}"

    print(f"  Total days: {group.total_days}")
    print(f"  Multiplier: {group.multiplier}")
    print("[OK] MultiDayGroup test passed!\n")


def test_slot_recommendation():
    """Test SlotRecommendation with multi-day fields."""
    print("Testing SlotRecommendation...")

    recipe = ScoredRecipe(
        title="Lasagne",
        url="https://example.com/lasagne",
        score=85.0,
        reasoning="Test",
        is_new=False,
        recipe_id=1,
    )

    # Test normal slot
    slot = SlotRecommendation(
        weekday="Sonntag",
        slot="Abendessen",
        recommendations=[recipe],
        prep_days=3,
    )

    assert not slot.is_reuse_slot, "Should not be a reuse slot"
    assert slot.prep_days == 3, "prep_days should be 3"
    print(f"  Normal slot: {slot}")

    # Test reuse slot
    reuse_slot = SlotRecommendation(
        weekday="Montag",
        slot="Abendessen",
        recommendations=[],
        reuse_from=("Sonntag", "Abendessen"),
    )

    assert reuse_slot.is_reuse_slot, "Should be a reuse slot"
    assert reuse_slot.selected_recipe is None, "Reuse slot should have no recipe"
    print(f"  Reuse slot: {reuse_slot}")

    print("[OK] SlotRecommendation test passed!\n")


def test_weekly_recommendation_multi_day():
    """Test WeeklyRecommendation multi-day methods."""
    print("Testing WeeklyRecommendation multi-day methods...")

    # Create a simple plan
    recipe = ScoredRecipe(
        title="Lasagne",
        url="https://example.com/lasagne",
        score=85.0,
        reasoning="Test",
        is_new=False,
        recipe_id=1,
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

    # Check reuse slots
    monday = plan.get_slot("Montag", "Abendessen")
    assert monday is not None
    assert monday.is_reuse_slot, "Monday should be a reuse slot"
    assert monday.reuse_from == ("Sonntag", "Abendessen")

    # Check get_recipe_for_slot
    recipe_for_monday = plan.get_recipe_for_slot("Montag", "Abendessen")
    assert recipe_for_monday is not None, "Should get recipe from primary slot"
    assert recipe_for_monday.title == "Lasagne"

    print(f"  Multi-day groups: {len(plan.multi_day_groups)}")
    print(f"  Primary slot prep_days: {sunday.prep_days}")
    print(f"  Reuse slot: {monday.is_reuse_slot}")

    # Test clear_multi_day
    result = plan.clear_multi_day("Montag", "Abendessen")
    assert result is True, "clear_multi_day should return True"
    assert monday.reuse_from is None, "Monday should no longer be a reuse slot"

    print("[OK] WeeklyRecommendation multi-day test passed!\n")


def test_json_serialization():
    """Test JSON serialization with multi-day groups."""
    print("Testing JSON serialization...")

    recipe = ScoredRecipe(
        title="Lasagne",
        url="https://example.com/lasagne",
        score=85.0,
        reasoning="Test",
        is_new=False,
        recipe_id=1,
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

    # Test from_dict
    restored_plan = WeeklyRecommendation.from_dict(data)
    assert len(restored_plan.multi_day_groups) == 1
    assert restored_plan.multi_day_groups[0].primary_weekday == "Sonntag"

    sunday = restored_plan.get_slot("Sonntag", "Abendessen")
    assert sunday.prep_days == 2

    monday = restored_plan.get_slot("Montag", "Abendessen")
    assert monday.is_reuse_slot

    print("[OK] JSON serialization test passed!\n")


if __name__ == "__main__":
    print("=" * 60)
    print("Issue #31 WIP Test Suite")
    print("=" * 60)
    print()

    test_multi_day_group()
    test_slot_recommendation()
    test_weekly_recommendation_multi_day()
    test_json_serialization()

    print("=" * 60)
    print("All WIP tests passed!")
    print("=" * 60)
