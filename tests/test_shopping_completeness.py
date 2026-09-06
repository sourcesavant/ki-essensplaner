import sqlite3
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from src.agents import recipe_search_agent
from src.agents.models import ScoredRecipe, SlotRecommendation, WeeklyRecommendation
from src.api.routers import shopping, weekly_plan
from src.api.schemas.shopping import ShoppingListResponse
from src.api.schemas.weekly_plan import SelectRecipeRequest, SelectRecipeUrlRequest
from src.core import database
from src.models.recipe import RecipeCreate
from src.profile.ingredient_parser import parse_ingredient
from src.shopping.shopping_list import generate_shopping_list, round_amount


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setattr(database, "ensure_directories", lambda: None)
    database.init_db()
    return database


def make_plan(ingredients, recipe_id=None, prep_days=1):
    recipe = ScoredRecipe("Test", "https://example.com/recipe", 1, "", False,
                          recipe_id=recipe_id, ingredients=ingredients, servings=2)
    return WeeklyRecommendation(week_start="2026-09-05", slots=[
        SlotRecommendation("Montag", "Mittagessen", [recipe], prep_days=prep_days)
    ])


def test_partial_cache_does_not_omit_ingredients(db):
    recipe = db.upsert_recipe(RecipeCreate(title="Test", source="test", ingredients=["200 g Reis", "1 Paprika"]))
    with db.get_connection() as conn:
        conn.execute("INSERT INTO parsed_ingredients (recipe_id, original, amount, unit, ingredient, base_ingredient) VALUES (?, ?, ?, ?, ?, ?)",
                     (recipe.id, "200 g Reis", 200, "gramm", "Reis", "reis"))
    result = generate_shopping_list(make_plan([], recipe.id), 2)
    assert {item.ingredient.lower() for item in result.items} == {"reis", "paprika"}
    assert result.missing_recipes == []


def test_update_invalidates_cache_and_uses_current_recipe(db):
    old = RecipeCreate(title="Test", source="test", source_url="https://example.com/recipe", ingredients=["200 g Reis"])
    recipe = db.upsert_recipe(old)
    with db.get_connection() as conn:
        conn.execute("INSERT INTO parsed_ingredients (recipe_id, original, ingredient, base_ingredient) VALUES (?, ?, ?, ?)",
                     (recipe.id, "200 g Reis", "reis", "reis"))
    db.upsert_recipe(old.model_copy(update={"ingredients": ["300 g Reis", "1 Paprika"]}))
    with db.get_connection() as conn:
        assert conn.execute("SELECT COUNT(*) FROM parsed_ingredients").fetchone()[0] == 0
    result = generate_shopping_list(make_plan(["200 g Reis"], recipe.id), 2)
    assert next(i.amount for i in result.items if i.ingredient == "reis") == 300
    assert len(result.items) == 2


def test_raw_ingredients_scale_for_household_and_reuse():
    plan = make_plan(["200 g Reis", "Salz nach Geschmack"], prep_days=3)
    plan.slots.append(SlotRecommendation("Dienstag", "Mittagessen", reuse_from=("Montag", "Mittagessen")))
    result = generate_shopping_list(plan, 4)
    assert next(i.amount for i in result.items if i.ingredient == "reis") == 1200
    assert any(i.ingredient == "Salz nach Geschmack" for i in result.items)
    assert result.recipe_count == 1


def test_missing_ingredients_are_reported():
    result = generate_shopping_list(make_plan([]), 2)
    assert result.items == []
    assert result.missing_recipes == ["Montag Mittagessen: Test"]
    assert ShoppingListResponse(**result.to_dict()).missing_recipes == result.missing_recipes


@pytest.mark.parametrize("amount,unit", [(4, "gramm"), (0.2, "teelöffel"), (0.01, "kilogramm")])
def test_small_quantities_stay_positive(amount, unit):
    assert round_amount(amount, unit) > 0


@pytest.mark.parametrize("line,amount", [("1/2 EL Öl", 0.5), ("½ EL Öl", 0.5), ("1 1/2 EL Öl", 1.5), ("2 x 400 g Tomaten", 800)])
def test_fraction_and_pack_quantities(line, amount):
    assert parse_ingredient(line).amount == amount


def test_ambiguous_quantity_preserved():
    result = generate_shopping_list(make_plan(["1-2 EL Öl"]), 4)
    assert result.items[0].ingredient == "1-2 EL Öl"
    assert result.items[0].amount is None


def test_checked_reopens_only_when_requirement_increases(db):
    old = {"amount": 200, "recipes": ["Montag"]}
    db.set_item_checked("week", "reis_gramm", True, old)
    assert db.get_checked_items("week", {"reis_gramm": old}) == {"reis_gramm"}
    assert db.get_checked_items("week", {"reis_gramm": {**old, "amount": 100}}) == {"reis_gramm"}
    assert db.get_checked_items("week", {"reis_gramm": {**old, "amount": 400}}) == set()
    assert db.get_checked_items("week") == set()


def test_unknown_quantity_reopens_for_additional_recipe(db):
    db.set_item_checked("week", "salz_", True, {"amount": None, "recipes": ["Montag"]})
    assert db.get_checked_items("week", {"salz_": {"amount": None, "recipes": ["Montag", "Dienstag"]}}) == set()


def test_checked_migration(tmp_path, monkeypatch):
    path = tmp_path / "legacy.db"
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE shopping_checked_items (item_key TEXT, week_start TEXT, PRIMARY KEY(item_key, week_start))")
        conn.execute("INSERT INTO shopping_checked_items VALUES ('reis_', 'week')")
    monkeypatch.setattr(database, "DB_PATH", path)
    monkeypatch.setattr(database, "ensure_directories", lambda: None)
    database.init_db()
    database.init_db()
    assert database.get_checked_items("week", {"reis_": {"amount": 1, "recipes": []}}) == set()


def test_manual_existing_empty_recipe_is_refetched(db, monkeypatch):
    stored = db.upsert_recipe(RecipeCreate(title="Test", source="test", source_url="https://example.com/recipe"))
    plan = make_plan([], stored.id)
    monkeypatch.setattr(weekly_plan, "load_weekly_plan", lambda: plan)
    monkeypatch.setattr(weekly_plan, "save_weekly_plan", lambda p: None)
    monkeypatch.setattr(weekly_plan, "scrape_recipe", lambda url: RecipeCreate(title="Test", source="test", source_url=url, ingredients=["200 g Reis"]))
    weekly_plan.select_recipe_url(SelectRecipeUrlRequest(weekday="Montag", slot="Mittagessen", recipe_url=stored.source_url), "test")
    assert plan.slots[0].selected_recipe.ingredients == ["200 g Reis"]
    assert generate_shopping_list(plan, 4).items[0].amount == 400


def test_failed_ingredient_fetch_does_not_save_selection(monkeypatch):
    plan = make_plan([])
    plan.slots[0].selected_index = -1
    monkeypatch.setattr(weekly_plan, "load_weekly_plan", lambda: plan)
    monkeypatch.setattr(weekly_plan, "get_recipe_by_url", lambda url: None)
    monkeypatch.setattr(weekly_plan, "scrape_recipe", lambda url: None)
    monkeypatch.setattr(weekly_plan, "save_weekly_plan", lambda p: pytest.fail("must not save"))
    with pytest.raises(HTTPException) as exc:
        weekly_plan.select_recipe(SelectRecipeRequest(weekday="Montag", slot="Mittagessen", recipe_index=0), "test")
    assert exc.value.status_code == 422
    assert plan.slots[0].selected_index == -1


def test_checked_api_detects_plan_change(db, monkeypatch):
    plan = make_plan(["200 g Reis"])
    monkeypatch.setattr(shopping, "load_weekly_plan", lambda: plan)
    monkeypatch.setattr("src.core.user_config.get_household_size", lambda: 2)
    shopping.toggle_checked(shopping.ToggleCheckedRequest(item_key="reis_gramm", checked=True), "test")
    assert shopping.get_checked("test").checked_items == ["reis_gramm"]
    plan.slots[0].prep_days = 2
    assert shopping.get_checked("test").checked_items == []


@pytest.mark.parametrize("cached", [False, True])
def test_generation_failure_only_keeps_recipes_with_known_ingredients(monkeypatch, cached):
    candidate = make_plan([]).slots[0].selected_recipe
    stored = SimpleNamespace(id=1, ingredients=["200 g Reis"], servings=2) if cached else None
    monkeypatch.setattr(recipe_search_agent, "get_recipe_by_url", lambda url: stored)
    monkeypatch.setattr(recipe_search_agent, "get_unavailable_strict_seasonal_title_ingredients", lambda *args: [])
    def fail(url):
        raise RuntimeError("scrape failed")
    monkeypatch.setattr("recipe_scrapers.scrape_me", fail)
    result = recipe_search_agent._load_recipe_details([candidate], SimpleNamespace(available_ingredients=[], month=9))
    assert len(result) == int(cached)
    if cached:
        assert result[0].ingredients == ["200 g Reis"]


def test_split_lists_preserve_all_items_and_report_missing(db, monkeypatch):
    plan = make_plan(["200 g Reis", "1 Paprika"])
    plan.slots.append(SlotRecommendation("Dienstag", "Abendessen", [make_plan([]).slots[0].selected_recipe]))
    monkeypatch.setattr(shopping, "load_weekly_plan", lambda: plan)
    monkeypatch.setattr("src.core.user_config.get_household_size", lambda: 2)
    monkeypatch.setattr("src.shopping.shopping_list.get_available_base_ingredients", lambda store: {"paprika"})
    full = shopping.get_shopping_list("test")
    split = shopping.get_split_shopping_list("test")
    assert sorted(i.ingredient for i in full.items) == sorted(i.ingredient for i in split.bioland + split.rewe)
    assert full.missing_recipes == split.missing_recipes == ["Dienstag Abendessen: Test"]
