"""Data models for the recipe search agent."""

import json
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from enum import Enum
from pathlib import Path

from src.core.config import LOCAL_DIR

# Path for saving weekly plans
WEEKLY_PLAN_FILE = LOCAL_DIR / "weekly_plan.json"


class SlotGroup(Enum):
    """Groups of meal slots by typical preparation effort."""

    QUICK = "quick"  # Fast meals: Mi/Do/Fr Mittagessen (15-20 min)
    NORMAL = "normal"  # Normal effort: Di-Fr Abendessen (30-40 min)
    ELABORATE = "elaborate"  # Elaborate meals: Mo/So Abendessen, Mo/Di Mittagessen (50-60 min)


# Mapping of weekday/slot to group
SLOT_GROUP_MAPPING: dict[tuple[str, str], SlotGroup] = {
    # Quick meals (weekday lunches, typically simple)
    ("Mittwoch", "Mittagessen"): SlotGroup.QUICK,
    ("Donnerstag", "Mittagessen"): SlotGroup.QUICK,
    ("Freitag", "Mittagessen"): SlotGroup.QUICK,
    # Normal effort (weekday dinners)
    ("Dienstag", "Abendessen"): SlotGroup.NORMAL,
    ("Mittwoch", "Abendessen"): SlotGroup.NORMAL,
    ("Donnerstag", "Abendessen"): SlotGroup.NORMAL,
    ("Freitag", "Abendessen"): SlotGroup.NORMAL,
    ("Samstag", "Mittagessen"): SlotGroup.NORMAL,
    # Elaborate meals (weekend dinners, Monday/Tuesday lunches)
    ("Montag", "Mittagessen"): SlotGroup.ELABORATE,
    ("Dienstag", "Mittagessen"): SlotGroup.ELABORATE,
    ("Samstag", "Abendessen"): SlotGroup.ELABORATE,
    ("Sonntag", "Mittagessen"): SlotGroup.ELABORATE,
    ("Sonntag", "Abendessen"): SlotGroup.ELABORATE,
    ("Montag", "Abendessen"): SlotGroup.ELABORATE,
}

# All weekdays in German
WEEKDAYS = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]

# Meal slots
MEAL_SLOTS = ["Mittagessen", "Abendessen"]


@dataclass
class ScoredRecipe:
    """A recipe with its score and metadata."""

    title: str
    url: str | None
    score: float
    reasoning: str
    is_new: bool  # True = from eatsmarter search, False = from DB
    recipe_id: int | None = None  # DB ID, None for new recipes
    prep_time_minutes: int | None = None
    calories: int | None = None
    ingredients: list[str] = field(default_factory=list)

    def __str__(self) -> str:
        source = "NEU" if self.is_new else "FAV"
        time_str = f"{self.prep_time_minutes}min" if self.prep_time_minutes else "?"
        return f"[{source}] {self.title} ({self.score:.0f}pt, {time_str})"


@dataclass
class SlotRecommendation:
    """Recommendations for a single meal slot."""

    weekday: str
    slot: str
    recommendations: list[ScoredRecipe] = field(default_factory=list)
    selected_index: int = 0  # Index of user-selected recipe (default: top recommendation)

    @property
    def slot_group(self) -> SlotGroup:
        """Get the effort group for this slot."""
        return SLOT_GROUP_MAPPING.get((self.weekday, self.slot), SlotGroup.NORMAL)

    @property
    def top_recipe(self) -> ScoredRecipe | None:
        """Get the top-scored recipe."""
        return self.recommendations[0] if self.recommendations else None

    @property
    def selected_recipe(self) -> ScoredRecipe | None:
        """Get the user-selected recipe."""
        if 0 <= self.selected_index < len(self.recommendations):
            return self.recommendations[self.selected_index]
        return self.top_recipe

    def select(self, index: int) -> bool:
        """Select a recipe by index. Returns True if valid selection."""
        if 0 <= index < len(self.recommendations):
            self.selected_index = index
            return True
        return False

    def __str__(self) -> str:
        selected = self.selected_recipe
        if selected:
            marker = "" if self.selected_index == 0 else f" [#{self.selected_index + 1}]"
            return f"{self.weekday} {self.slot}: {selected.title} ({selected.score:.0f}pt){marker}"
        return f"{self.weekday} {self.slot}: Keine Empfehlung"


@dataclass
class WeeklyRecommendation:
    """Complete weekly meal plan recommendation."""

    generated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    week_start: str = field(default_factory=lambda: _get_week_start().isoformat())
    favorites_count: int = 0
    new_count: int = 0
    slots: list[SlotRecommendation] = field(default_factory=list)

    @property
    def total_slots(self) -> int:
        return len(self.slots)

    @property
    def favorites_ratio(self) -> float:
        """Actual ratio of favorites (target: 0.6)."""
        total = self.favorites_count + self.new_count
        return self.favorites_count / total if total > 0 else 0.0

    def get_slot(self, weekday: str, slot: str) -> SlotRecommendation | None:
        """Get recommendation for a specific slot."""
        for s in self.slots:
            if s.weekday == weekday and s.slot == slot:
                return s
        return None

    def select_recipe(self, weekday: str, slot: str, index: int) -> bool:
        """Select a recipe for a specific slot. Returns True if successful."""
        slot_rec = self.get_slot(weekday, slot)
        if slot_rec:
            return slot_rec.select(index)
        return False

    def get_selected_recipes(self) -> list[tuple[str, str, ScoredRecipe]]:
        """Get all selected recipes as (weekday, slot, recipe) tuples."""
        result = []
        for slot in self.slots:
            recipe = slot.selected_recipe
            if recipe:
                result.append((slot.weekday, slot.slot, recipe))
        return result

    def summary(self) -> str:
        """Generate a summary of the weekly plan."""
        lines = [
            f"Wochenplan für Woche ab {self.week_start}",
            f"Generiert: {self.generated_at[:10]}",
            f"Favoriten: {self.favorites_count} ({self.favorites_ratio:.0%})",
            f"Neue Rezepte: {self.new_count} ({1 - self.favorites_ratio:.0%})",
            "",
        ]
        for slot in self.slots:
            lines.append(str(slot))
        return "\n".join(lines)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "generated_at": self.generated_at,
            "week_start": self.week_start,
            "favorites_count": self.favorites_count,
            "new_count": self.new_count,
            "slots": [
                {
                    "weekday": s.weekday,
                    "slot": s.slot,
                    "selected_index": s.selected_index,
                    "recommendations": [
                        {
                            "title": r.title,
                            "url": r.url,
                            "score": r.score,
                            "reasoning": r.reasoning,
                            "is_new": r.is_new,
                            "recipe_id": r.recipe_id,
                            "prep_time_minutes": r.prep_time_minutes,
                            "calories": r.calories,
                            "ingredients": r.ingredients,
                        }
                        for r in s.recommendations
                    ],
                }
                for s in self.slots
            ],
        }

    def to_json(self, indent: int = 2) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)

    @classmethod
    def from_dict(cls, data: dict) -> "WeeklyRecommendation":
        """Create from dictionary."""
        slots = []
        for s_data in data.get("slots", []):
            recommendations = [
                ScoredRecipe(
                    title=r["title"],
                    url=r.get("url"),
                    score=r["score"],
                    reasoning=r.get("reasoning", ""),
                    is_new=r.get("is_new", True),
                    recipe_id=r.get("recipe_id"),
                    prep_time_minutes=r.get("prep_time_minutes"),
                    calories=r.get("calories"),
                    ingredients=r.get("ingredients", []),
                )
                for r in s_data.get("recommendations", [])
            ]
            slots.append(
                SlotRecommendation(
                    weekday=s_data["weekday"],
                    slot=s_data["slot"],
                    recommendations=recommendations,
                    selected_index=s_data.get("selected_index", 0),
                )
            )

        return cls(
            generated_at=data.get("generated_at", datetime.now().isoformat()),
            week_start=data.get("week_start", _get_week_start().isoformat()),
            favorites_count=data.get("favorites_count", 0),
            new_count=data.get("new_count", 0),
            slots=slots,
        )

    @classmethod
    def from_json(cls, json_str: str) -> "WeeklyRecommendation":
        """Create from JSON string."""
        return cls.from_dict(json.loads(json_str))


def _get_week_start() -> date:
    """Get the Monday of the current week."""
    today = date.today()
    return today - __import__("datetime").timedelta(days=today.weekday())


def save_weekly_plan(plan: WeeklyRecommendation, path: Path | None = None) -> Path:
    """Save a weekly plan to JSON file.

    Args:
        plan: The weekly plan to save
        path: Optional custom path, defaults to WEEKLY_PLAN_FILE

    Returns:
        Path where the plan was saved
    """
    save_path = path or WEEKLY_PLAN_FILE
    save_path.parent.mkdir(parents=True, exist_ok=True)

    with open(save_path, "w", encoding="utf-8") as f:
        f.write(plan.to_json())

    return save_path


def load_weekly_plan(path: Path | None = None) -> WeeklyRecommendation | None:
    """Load a weekly plan from JSON file.

    Args:
        path: Optional custom path, defaults to WEEKLY_PLAN_FILE

    Returns:
        WeeklyRecommendation or None if file doesn't exist
    """
    load_path = path or WEEKLY_PLAN_FILE

    if not load_path.exists():
        return None

    try:
        with open(load_path, "r", encoding="utf-8") as f:
            return WeeklyRecommendation.from_json(f.read())
    except (json.JSONDecodeError, KeyError) as e:
        print(f"Error loading weekly plan: {e}")
        return None


@dataclass
class SearchQuery:
    """A search query for eatsmarter."""

    group: SlotGroup
    ingredients: list[str]
    max_time: int | None = None

    def __str__(self) -> str:
        return f"{self.group.value}: {', '.join(self.ingredients[:3])} (max {self.max_time}min)"
