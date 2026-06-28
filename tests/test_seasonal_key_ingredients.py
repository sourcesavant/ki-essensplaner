from src.models.recipe import Recipe
from src.scoring.recipe_scorer import (
    ScoringContext,
    get_unavailable_strict_seasonal_title_ingredients,
    is_recipe_viable,
)
from src.scoring.seasonality import is_in_season


def _context(month: int, available: set[str] | None = None) -> ScoringContext:
    return ScoringContext(
        weekday="Montag",
        meal_slot="Abendessen",
        profile={},
        available_ingredients=available or set(),
        month=month,
    )


def test_seasonality_aliases_handle_ascii_umlaut_variants() -> None:
    assert is_in_season("baerlauch", 6) is False
    assert is_in_season("kuerbis", 6) is False
    assert is_in_season("gruenkohl", 6) is False


def test_out_of_season_spargel_title_is_not_viable_when_unavailable() -> None:
    recipe = Recipe(
        title="Spargel-Risotto",
        source="test",
        ingredients=[],
    )

    viable, unavailable, ratio = is_recipe_viable(recipe, _context(month=7))

    assert viable is False
    assert ratio == 0.0
    assert unavailable == ["spargel nicht saisonal und nicht bei Bioland verf\u00fcgbar"]


def test_out_of_season_baerlauch_title_is_not_viable_when_unavailable() -> None:
    recipe = Recipe(
        title="B\u00e4rlauch Pasta",
        source="test",
        ingredients=[],
    )

    viable, unavailable, _ = is_recipe_viable(recipe, _context(month=6))

    assert viable is False
    assert unavailable == ["b\u00e4rlauch nicht saisonal und nicht bei Bioland verf\u00fcgbar"]


def test_out_of_season_hokkaido_title_is_not_viable_when_unavailable() -> None:
    recipe = Recipe(
        title="Hokkaido-Curry",
        source="test",
        ingredients=[],
    )

    viable, unavailable, _ = is_recipe_viable(recipe, _context(month=6))

    assert viable is False
    assert unavailable == ["k\u00fcrbis nicht saisonal und nicht bei Bioland verf\u00fcgbar"]


def test_strict_seasonal_title_ingredient_allowed_when_shop_has_it() -> None:
    unavailable = get_unavailable_strict_seasonal_title_ingredients(
        "Spargel-Risotto",
        available_ingredients={"spargel"},
        month=7,
    )

    assert unavailable == []


def test_additional_strict_seasonal_title_ingredients_are_blocked() -> None:
    cases = [
        ("Erdbeer-Salat", 2, "erdbeere"),
        ("Rhabarber-Kompott", 9, "rhabarber"),
        ("Pfifferling-Risotto", 12, "pfifferling"),
        ("Gr\u00fcnkohl-Pasta", 6, "gr\u00fcnkohl"),
        ("Rosenkohl-Auflauf", 6, "rosenkohl"),
    ]

    for title, month, expected in cases:
        viable, unavailable, ratio = is_recipe_viable(
            Recipe(title=title, source="test", ingredients=[]),
            _context(month=month),
        )

        assert viable is False
        assert ratio == 0.0
        assert unavailable == [
            f"{expected} nicht saisonal und nicht bei Bioland verf\u00fcgbar"
        ]
