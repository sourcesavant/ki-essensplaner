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
    servings: int | None = None  # Number of servings in original recipe

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
    reuse_from: tuple[str, str] | None = None  # (weekday, slot) if reusing from another slot
    prep_days: int = 1  # Number of days this recipe is prepped for

    @property
    def slot_group(self) -> SlotGroup:
        """Get the effort group for this slot."""
        return SLOT_GROUP_MAPPING.get((self.weekday, self.slot), SlotGroup.NORMAL)

    @property
    def is_reuse_slot(self) -> bool:
        """True if this slot reuses a recipe from another slot."""
        return self.reuse_from is not None

    @property
    def top_recipe(self) -> ScoredRecipe | None:
        """Get the top-scored recipe."""
        return self.recommendations[0] if self.recommendations else None

    @property
    def selected_recipe(self) -> ScoredRecipe | None:
        """Get the user-selected recipe (or None if reuse slot)."""
        if self.is_reuse_slot:
            return None  # Recipe comes from primary slot
        if self.selected_index < 0:
            return None
        if 0 <= self.selected_index < len(self.recommendations):
            return self.recommendations[self.selected_index]
        return self.top_recipe

    def select(self, index: int) -> bool:
        """Select a recipe by index. Returns True if valid selection."""
        if index == -1:
            self.selected_index = -1
            return True
        if 0 <= index < len(self.recommendations):
            self.selected_index = index
            return True
        return False

    def __str__(self) -> str:
        if self.is_reuse_slot:
            return f"{self.weekday} {self.slot}: [Vom {self.reuse_from[0]} {self.reuse_from[1]}]"
        if self.selected_index < 0:
            return f"{self.weekday} {self.slot}: Kein Rezept"
        selected = self.selected_recipe
        if selected:
            marker = "" if self.selected_index == 0 else f" [#{self.selected_index + 1}]"
            prep_marker = f" (×{self.prep_days})" if self.prep_days > 1 else ""
            return f"{self.weekday} {self.slot}: {selected.title} ({selected.score:.0f}pt){marker}{prep_marker}"
        return f"{self.weekday} {self.slot}: Keine Empfehlung"


@dataclass
class MultiDayGroup:
    """Group of slots that share the same recipe (meal prep)."""

    primary_weekday: str
    primary_slot: str
    reuse_slots: list[tuple[str, str]] = field(default_factory=list)

    @property
    def total_days(self) -> int:
        """Total number of days this recipe is used."""
        return 1 + len(self.reuse_slots)

    @property
    def multiplier(self) -> float:
        """Quantity multiplier for shopping list."""
        return float(self.total_days)


@dataclass
class WeeklyRecommendation:
    """Complete weekly meal plan recommendation."""

    generated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    week_start: str = field(default_factory=lambda: _get_week_start().isoformat())
    completed_at: str | None = None
    favorites_count: int = 0
    new_count: int = 0
    slots: list[SlotRecommendation] = field(default_factory=list)
    multi_day_groups: list[MultiDayGroup] = field(default_factory=list)

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

    def get_recipe_for_slot(self, weekday: str, slot: str) -> ScoredRecipe | None:
        """Get recipe for slot, following reuse reference if needed."""
        target = self.get_slot(weekday, slot)
        if not target:
            return None

        if target.reuse_from:
            primary_weekday, primary_slot = target.reuse_from
            primary = self.get_slot(primary_weekday, primary_slot)
            if primary:
                return primary.selected_recipe
            return None

        return target.selected_recipe

    def set_multi_day(
        self,
        primary_weekday: str,
        primary_slot: str,
        reuse_slots: list[tuple[str, str]],
    ) -> bool:
        """Configure a recipe to be used for multiple days.

        Args:
            primary_weekday: Weekday when cooking
            primary_slot: Meal slot (Mittagessen/Abendessen)
            reuse_slots: List of (weekday, slot) tuples to reuse this recipe

        Returns:
            True if successful, False otherwise
        """
        primary = self.get_slot(primary_weekday, primary_slot)
        if not primary:
            return False

        # Configure primary slot
        primary.prep_days = 1 + len(reuse_slots)
        primary.reuse_from = None

        # Configure reuse slots
        for weekday, slot_name in reuse_slots:
            reuse = self.get_slot(weekday, slot_name)
            if reuse:
                reuse.reuse_from = (primary_weekday, primary_slot)
                reuse.recommendations = []  # No own recommendations
                reuse.prep_days = 1

        # Save group
        group = MultiDayGroup(
            primary_weekday=primary_weekday,
            primary_slot=primary_slot,
            reuse_slots=reuse_slots,
        )

        # Remove old group for this primary if exists
        self.multi_day_groups = [
            g
            for g in self.multi_day_groups
            if not (g.primary_weekday == primary_weekday and g.primary_slot == primary_slot)
        ]
        self.multi_day_groups.append(group)

        return True

    def clear_multi_day(self, weekday: str, slot: str) -> bool:
        """Remove multi-day configuration for a slot.

        Args:
            weekday: Weekday
            slot: Meal slot

        Returns:
            True if successful, False otherwise
        """
        target = self.get_slot(weekday, slot)
        if not target:
            return False

        # If it's a reuse slot, only free this one
        if target.reuse_from:
            primary_weekday, primary_slot = target.reuse_from
            target.reuse_from = None

            # Update primary slot
            primary = self.get_slot(primary_weekday, primary_slot)
            if primary:
                primary.prep_days = max(1, primary.prep_days - 1)

            # Update group
            for group in self.multi_day_groups:
                if group.primary_weekday == primary_weekday and group.primary_slot == primary_slot:
                    group.reuse_slots = [
                        (w, s) for w, s in group.reuse_slots if not (w == weekday and s == slot)
                    ]
                    if not group.reuse_slots:
                        self.multi_day_groups.remove(group)
                    break
        else:
            # It's a primary slot - free all reuse slots
            for reuse_weekday, reuse_slot in self._get_reuse_slots_for(weekday, slot):
                reuse = self.get_slot(reuse_weekday, reuse_slot)
                if reuse:
                    reuse.reuse_from = None

            target.prep_days = 1

            # Remove group
            self.multi_day_groups = [
                g
                for g in self.multi_day_groups
                if not (g.primary_weekday == weekday and g.primary_slot == slot)
            ]

        return True

    def _get_reuse_slots_for(self, weekday: str, slot: str) -> list[tuple[str, str]]:
        """Get all reuse slots for a primary slot."""
        for group in self.multi_day_groups:
            if group.primary_weekday == weekday and group.primary_slot == slot:
                return group.reuse_slots
        return []

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
            "completed_at": self.completed_at,
            "favorites_count": self.favorites_count,
            "new_count": self.new_count,
            "multi_day_groups": [
                {
                    "primary_weekday": g.primary_weekday,
                    "primary_slot": g.primary_slot,
                    "reuse_slots": g.reuse_slots,
                }
                for g in self.multi_day_groups
            ],
            "slots": [
                {
                    "weekday": s.weekday,
                    "slot": s.slot,
                    "selected_index": s.selected_index,
                    "reuse_from": s.reuse_from,
                    "prep_days": s.prep_days,
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
                            "servings": r.servings,
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
                    servings=r.get("servings"),
                )
                for r in s_data.get("recommendations", [])
            ]

            # Parse reuse_from tuple
            reuse_from = s_data.get("reuse_from")
            if reuse_from and isinstance(reuse_from, list) and len(reuse_from) == 2:
                reuse_from = tuple(reuse_from)
            elif reuse_from and isinstance(reuse_from, tuple):
                pass  # Already a tuple
            else:
                reuse_from = None

            slots.append(
                SlotRecommendation(
                    weekday=s_data["weekday"],
                    slot=s_data["slot"],
                    recommendations=recommendations,
                    selected_index=s_data.get("selected_index", 0),
                    reuse_from=reuse_from,
                    prep_days=s_data.get("prep_days", 1),
                )
            )

        # Parse multi_day_groups
        multi_day_groups = []
        for g_data in data.get("multi_day_groups", []):
            # Convert reuse_slots to list of tuples
            reuse_slots = [
                tuple(rs) if isinstance(rs, list) else rs
                for rs in g_data.get("reuse_slots", [])
            ]
            multi_day_groups.append(
                MultiDayGroup(
                    primary_weekday=g_data["primary_weekday"],
                    primary_slot=g_data["primary_slot"],
                    reuse_slots=reuse_slots,
                )
            )

        return cls(
            generated_at=data.get("generated_at", datetime.now().isoformat()),
            week_start=data.get("week_start", _get_week_start().isoformat()),
            completed_at=data.get("completed_at"),
            favorites_count=data.get("favorites_count", 0),
            new_count=data.get("new_count", 0),
            slots=slots,
            multi_day_groups=multi_day_groups,
        )

    @classmethod
    def from_json(cls, json_str: str) -> "WeeklyRecommendation":
        """Create from JSON string."""
        return cls.from_dict(json.loads(json_str))


def _get_week_start() -> date:
    """Get the Saturday of the next week (or current week if today is Saturday)."""
    today = date.today()
    # Saturday = 5 in weekday (0=Monday, 6=Sunday)
    days_until_saturday = (5 - today.weekday()) % 7
    # If today is Saturday, use next Saturday (7 days from now)
    if days_until_saturday == 0:
        days_until_saturday = 7
    return today + __import__("datetime").timedelta(days=days_until_saturday)


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
