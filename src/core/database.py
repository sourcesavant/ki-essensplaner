"""SQLite database setup and CRUD operations."""

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from typing import Generator

from src.core.config import DB_PATH, ensure_directories
from src.models.meal_plan import DayOfWeek, Meal, MealCreate, MealPlan, MealPlanCreate, MealSlot
from src.models.recipe import Recipe, RecipeCreate

SCHEMA = """
-- Recipes (from scraping + OneNote)
CREATE TABLE IF NOT EXISTS recipes (
    id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    source TEXT,
    source_url TEXT,
    prep_time_minutes INTEGER,
    ingredients TEXT,
    instructions TEXT,
    calories INTEGER,
    fat_g REAL,
    protein_g REAL,
    carbs_g REAL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Meal plans from OneNote
CREATE TABLE IF NOT EXISTS meal_plans (
    id INTEGER PRIMARY KEY,
    onenote_page_id TEXT UNIQUE,
    week_start DATE,
    raw_content TEXT,
    parsed_at TIMESTAMP
);

-- Individual meals
CREATE TABLE IF NOT EXISTS meals (
    id INTEGER PRIMARY KEY,
    meal_plan_id INTEGER REFERENCES meal_plans(id),
    day_of_week INTEGER,
    slot TEXT,
    recipe_id INTEGER REFERENCES recipes(id),
    recipe_title TEXT
);

-- Parsed/normalized ingredients
CREATE TABLE IF NOT EXISTS parsed_ingredients (
    id INTEGER PRIMARY KEY,
    recipe_id INTEGER REFERENCES recipes(id),
    original TEXT,
    amount REAL,
    unit TEXT,
    ingredient TEXT,
    base_ingredient TEXT
);

-- Index for faster lookups
CREATE INDEX IF NOT EXISTS idx_recipes_source ON recipes(source);
CREATE INDEX IF NOT EXISTS idx_meals_plan_id ON meals(meal_plan_id);
CREATE INDEX IF NOT EXISTS idx_meal_plans_page_id ON meal_plans(onenote_page_id);
CREATE INDEX IF NOT EXISTS idx_parsed_ingredients_recipe ON parsed_ingredients(recipe_id);
CREATE INDEX IF NOT EXISTS idx_parsed_ingredients_base ON parsed_ingredients(base_ingredient);
"""


def init_db() -> None:
    """Initialize the database with schema."""
    ensure_directories()
    with get_connection() as conn:
        conn.executescript(SCHEMA)


@contextmanager
def get_connection() -> Generator[sqlite3.Connection, None, None]:
    """Get a database connection with row factory."""
    ensure_directories()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# Recipe CRUD operations


def create_recipe(recipe: RecipeCreate) -> Recipe:
    """Create a new recipe."""
    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO recipes (title, source, source_url, prep_time_minutes, ingredients, instructions,
                                 calories, fat_g, protein_g, carbs_g)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                recipe.title,
                recipe.source,
                recipe.source_url,
                recipe.prep_time_minutes,
                json.dumps(recipe.ingredients),
                recipe.instructions,
                recipe.calories,
                recipe.fat_g,
                recipe.protein_g,
                recipe.carbs_g,
            ),
        )
        return Recipe(
            id=cursor.lastrowid,
            title=recipe.title,
            source=recipe.source,
            source_url=recipe.source_url,
            prep_time_minutes=recipe.prep_time_minutes,
            ingredients=recipe.ingredients,
            instructions=recipe.instructions,
            calories=recipe.calories,
            fat_g=recipe.fat_g,
            protein_g=recipe.protein_g,
            carbs_g=recipe.carbs_g,
            created_at=datetime.now(),
        )


def get_recipe(recipe_id: int) -> Recipe | None:
    """Get a recipe by ID."""
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM recipes WHERE id = ?", (recipe_id,)).fetchone()
        if row:
            return _row_to_recipe(row)
        return None


def get_recipe_by_url(url: str) -> Recipe | None:
    """Get a recipe by source URL."""
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM recipes WHERE source_url = ?", (url,)).fetchone()
        if row:
            return _row_to_recipe(row)
        return None


def get_recipes_by_source(source: str) -> list[Recipe]:
    """Get all recipes from a specific source."""
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM recipes WHERE source = ?", (source,)).fetchall()
        return [_row_to_recipe(row) for row in rows]


def get_all_recipes() -> list[Recipe]:
    """Get all recipes."""
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM recipes").fetchall()
        return [_row_to_recipe(row) for row in rows]


def upsert_recipe(recipe: RecipeCreate) -> Recipe:
    """Insert or update a recipe by source_url."""
    if recipe.source_url:
        existing = get_recipe_by_url(recipe.source_url)
        if existing:
            with get_connection() as conn:
                conn.execute(
                    """
                    UPDATE recipes
                    SET title = ?, source = ?, prep_time_minutes = ?, ingredients = ?, instructions = ?,
                        calories = ?, fat_g = ?, protein_g = ?, carbs_g = ?
                    WHERE source_url = ?
                    """,
                    (
                        recipe.title,
                        recipe.source,
                        recipe.prep_time_minutes,
                        json.dumps(recipe.ingredients),
                        recipe.instructions,
                        recipe.calories,
                        recipe.fat_g,
                        recipe.protein_g,
                        recipe.carbs_g,
                        recipe.source_url,
                    ),
                )
            return Recipe(
                id=existing.id,
                title=recipe.title,
                source=recipe.source,
                source_url=recipe.source_url,
                prep_time_minutes=recipe.prep_time_minutes,
                ingredients=recipe.ingredients,
                instructions=recipe.instructions,
                calories=recipe.calories,
                fat_g=recipe.fat_g,
                protein_g=recipe.protein_g,
                carbs_g=recipe.carbs_g,
                created_at=existing.created_at,
            )
    return create_recipe(recipe)


def _row_to_recipe(row: sqlite3.Row) -> Recipe:
    """Convert a database row to a Recipe model."""
    ingredients = json.loads(row["ingredients"]) if row["ingredients"] else []
    return Recipe(
        id=row["id"],
        title=row["title"],
        source=row["source"],
        source_url=row["source_url"],
        prep_time_minutes=row["prep_time_minutes"],
        ingredients=ingredients,
        instructions=row["instructions"],
        calories=row["calories"] if "calories" in row.keys() else None,
        fat_g=row["fat_g"] if "fat_g" in row.keys() else None,
        protein_g=row["protein_g"] if "protein_g" in row.keys() else None,
        carbs_g=row["carbs_g"] if "carbs_g" in row.keys() else None,
        created_at=row["created_at"],
    )


# MealPlan CRUD operations


def create_meal_plan(meal_plan: MealPlanCreate) -> MealPlan:
    """Create a new meal plan with meals."""
    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO meal_plans (onenote_page_id, week_start, raw_content, parsed_at)
            VALUES (?, ?, ?, ?)
            """,
            (
                meal_plan.onenote_page_id,
                meal_plan.week_start.isoformat() if meal_plan.week_start else None,
                meal_plan.raw_content,
                datetime.now().isoformat(),
            ),
        )
        plan_id = cursor.lastrowid

        meals = []
        for meal_data in meal_plan.meals:
            meal = _create_meal(conn, plan_id, meal_data)
            meals.append(meal)

        return MealPlan(
            id=plan_id,
            onenote_page_id=meal_plan.onenote_page_id,
            week_start=meal_plan.week_start,
            raw_content=meal_plan.raw_content,
            parsed_at=datetime.now(),
            meals=meals,
        )


def get_meal_plan(plan_id: int) -> MealPlan | None:
    """Get a meal plan by ID with all meals."""
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM meal_plans WHERE id = ?", (plan_id,)).fetchone()
        if row:
            return _row_to_meal_plan(conn, row)
        return None


def get_meal_plan_by_page_id(page_id: str) -> MealPlan | None:
    """Get a meal plan by OneNote page ID."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM meal_plans WHERE onenote_page_id = ?", (page_id,)
        ).fetchone()
        if row:
            return _row_to_meal_plan(conn, row)
        return None


def get_all_meal_plans() -> list[MealPlan]:
    """Get all meal plans with their meals."""
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM meal_plans ORDER BY week_start DESC").fetchall()
        return [_row_to_meal_plan(conn, row) for row in rows]


def upsert_meal_plan(meal_plan: MealPlanCreate) -> MealPlan:
    """Insert or update a meal plan by onenote_page_id."""
    if meal_plan.onenote_page_id:
        existing = get_meal_plan_by_page_id(meal_plan.onenote_page_id)
        if existing:
            with get_connection() as conn:
                conn.execute(
                    """
                    UPDATE meal_plans
                    SET week_start = ?, raw_content = ?, parsed_at = ?
                    WHERE onenote_page_id = ?
                    """,
                    (
                        meal_plan.week_start.isoformat() if meal_plan.week_start else None,
                        meal_plan.raw_content,
                        datetime.now().isoformat(),
                        meal_plan.onenote_page_id,
                    ),
                )
                # Delete old meals and recreate
                conn.execute("DELETE FROM meals WHERE meal_plan_id = ?", (existing.id,))
                meals = []
                for meal_data in meal_plan.meals:
                    meal = _create_meal(conn, existing.id, meal_data)
                    meals.append(meal)

            return MealPlan(
                id=existing.id,
                onenote_page_id=meal_plan.onenote_page_id,
                week_start=meal_plan.week_start,
                raw_content=meal_plan.raw_content,
                parsed_at=datetime.now(),
                meals=meals,
            )
    return create_meal_plan(meal_plan)


def _create_meal(conn: sqlite3.Connection, plan_id: int, meal: MealCreate) -> Meal:
    """Create a meal entry."""
    cursor = conn.execute(
        """
        INSERT INTO meals (meal_plan_id, day_of_week, slot, recipe_id, recipe_title)
        VALUES (?, ?, ?, ?, ?)
        """,
        (plan_id, meal.day_of_week.value, meal.slot.value, meal.recipe_id, meal.recipe_title),
    )
    return Meal(
        id=cursor.lastrowid,
        meal_plan_id=plan_id,
        day_of_week=meal.day_of_week,
        slot=meal.slot,
        recipe_id=meal.recipe_id,
        recipe_title=meal.recipe_title,
    )


def _row_to_meal_plan(conn: sqlite3.Connection, row: sqlite3.Row) -> MealPlan:
    """Convert a database row to a MealPlan model with meals."""
    meal_rows = conn.execute(
        "SELECT * FROM meals WHERE meal_plan_id = ?", (row["id"],)
    ).fetchall()
    meals = [_row_to_meal(meal_row) for meal_row in meal_rows]

    return MealPlan(
        id=row["id"],
        onenote_page_id=row["onenote_page_id"],
        week_start=row["week_start"],
        raw_content=row["raw_content"],
        parsed_at=row["parsed_at"],
        meals=meals,
    )


def _row_to_meal(row: sqlite3.Row) -> Meal:
    """Convert a database row to a Meal model."""
    return Meal(
        id=row["id"],
        meal_plan_id=row["meal_plan_id"],
        day_of_week=DayOfWeek(row["day_of_week"]),
        slot=MealSlot(row["slot"]),
        recipe_id=row["recipe_id"],
        recipe_title=row["recipe_title"],
    )
