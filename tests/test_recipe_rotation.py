from src.agents.models import ScoredRecipe, SlotRecommendation, WeeklyRecommendation
from src.agents.recipe_search_agent import (
    _filter_and_boost_favorites_by_rotation,
    _filter_new_recipes_by_rotation,
    _filter_slot_recommendations_by_banned_keys,
    _get_last_plan_recipe_keys,
    _recipe_key,
    _select_unique_recipes,
)


def _recipe(title: str, url: str | None, score: float, recipe_id: int | None = None) -> ScoredRecipe:
    return ScoredRecipe(
        title=title,
        url=url,
        score=score,
        reasoning="test",
        is_new=False,
        recipe_id=recipe_id,
    )


def test_last_plan_keys_use_selected_recipe_only() -> None:
    slot_1 = SlotRecommendation(
        weekday="Montag",
        slot="Mittagessen",
        recommendations=[
            _recipe("A1", "https://example.com/a1", 80),
            _recipe("A2", "https://example.com/a2", 79),
        ],
        selected_index=1,
    )
    slot_2 = SlotRecommendation(
        weekday="Dienstag",
        slot="Abendessen",
        recommendations=[_recipe("B1", "https://example.com/b1", 78)],
        selected_index=0,
    )
    plan = WeeklyRecommendation(slots=[slot_1, slot_2])

    keys = _get_last_plan_recipe_keys(plan)

    assert ("url", "https://example.com/a2") in keys
    assert ("url", "https://example.com/b1") in keys
    assert ("url", "https://example.com/a1") not in keys


def test_select_unique_recipes_skips_banned_first_candidate() -> None:
    banned = _recipe("Banned", "https://example.com/banned", 90)
    allowed = _recipe("Allowed", "https://example.com/allowed", 80)
    slot = SlotRecommendation(
        weekday="Montag",
        slot="Mittagessen",
        recommendations=[banned, allowed],
    )

    _select_unique_recipes(
        recommendations=[slot],
        group_id_by_slot={},
        planned_reuse_slots=set(),
        banned_keys={_recipe_key(banned)},
    )

    assert slot.selected_index == 1
    assert slot.selected_recipe is not None
    assert slot.selected_recipe.title == "Allowed"


def test_select_unique_recipes_marks_slot_unselected_when_all_banned() -> None:
    banned = _recipe("Banned", "https://example.com/banned", 90)
    slot = SlotRecommendation(
        weekday="Montag",
        slot="Mittagessen",
        recommendations=[banned],
    )

    _select_unique_recipes(
        recommendations=[slot],
        group_id_by_slot={},
        planned_reuse_slots=set(),
        banned_keys={_recipe_key(banned)},
    )

    assert slot.selected_index == -1
    assert slot.selected_recipe is None


def test_filter_and_boost_favorites_applies_cooldown_and_bonus() -> None:
    too_recent = _recipe("Too Recent", "https://example.com/r1", 70, recipe_id=1)
    eligible = _recipe("Eligible", "https://example.com/r2", 70, recipe_id=2)
    never_seen = _recipe("Never Seen", "https://example.com/r3", 65, recipe_id=3)

    recency = {
        ("url", "https://example.com/r1"): 2,
        ("url", "https://example.com/r2"): 3,
    }

    result = _filter_and_boost_favorites_by_rotation(
        favorites=[too_recent, eligible, never_seen],
        recency_map=recency,
        no_repeat_weeks=1,
        favorite_min_return_weeks=3,
        bonus_per_week=2.0,
        bonus_max=10.0,
    )

    titles = [r.title for r in result]
    assert "Too Recent" not in titles
    assert "Eligible" in titles
    assert "Never Seen" in titles

    eligible_recipe = next(r for r in result if r.title == "Eligible")
    assert eligible_recipe.score == 72.0


def test_filter_new_recipes_applies_no_repeat_window() -> None:
    recent = ScoredRecipe(
        title="Recent",
        url="https://example.com/new-1",
        score=60,
        reasoning="",
        is_new=True,
    )
    older = ScoredRecipe(
        title="Older",
        url="https://example.com/new-2",
        score=59,
        reasoning="",
        is_new=True,
    )
    unseen = ScoredRecipe(
        title="Unseen",
        url="https://example.com/new-3",
        score=58,
        reasoning="",
        is_new=True,
    )
    recency = {
        ("url", "https://example.com/new-1"): 1,
        ("url", "https://example.com/new-2"): 2,
    }

    filtered = _filter_new_recipes_by_rotation(
        recipes=[recent, older, unseen],
        recency_map=recency,
        no_repeat_weeks=1,
    )

    assert [r.title for r in filtered] == ["Older", "Unseen"]


def test_filter_slot_recommendations_removes_banned_alternatives() -> None:
    banned = _recipe("Banned", "https://example.com/banned", 90)
    allowed = _recipe("Allowed", "https://example.com/allowed", 80)
    slot = SlotRecommendation(
        weekday="Freitag",
        slot="Abendessen",
        recommendations=[banned, allowed],
    )

    _filter_slot_recommendations_by_banned_keys(
        recommendations=[slot],
        banned_keys={_recipe_key(banned)},
    )

    assert [r.title for r in slot.recommendations] == ["Allowed"]
