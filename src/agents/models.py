"""Data models for the recipe search agent."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


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

    @property
    def slot_group(self) -> SlotGroup:
        """Get the effort group for this slot."""
        return SLOT_GROUP_MAPPING.get((self.weekday, self.slot), SlotGroup.NORMAL)

    @property
    def top_recipe(self) -> ScoredRecipe | None:
        """Get the top-scored recipe."""
        return self.recommendations[0] if self.recommendations else None

    def __str__(self) -> str:
        top = self.top_recipe
        if top:
            return f"{self.weekday} {self.slot}: {top.title} ({top.score:.0f}pt)"
        return f"{self.weekday} {self.slot}: Keine Empfehlung"


@dataclass
class WeeklyRecommendation:
    """Complete weekly meal plan recommendation."""

    generated_at: str = field(default_factory=lambda: datetime.now().isoformat())
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

    def summary(self) -> str:
        """Generate a summary of the weekly plan."""
        lines = [
            f"Wochenplan generiert: {self.generated_at[:10]}",
            f"Favoriten: {self.favorites_count} ({self.favorites_ratio:.0%})",
            f"Neue Rezepte: {self.new_count} ({1 - self.favorites_ratio:.0%})",
            "",
        ]
        for slot in self.slots:
            lines.append(str(slot))
        return "\n".join(lines)


@dataclass
class SearchQuery:
    """A search query for eatsmarter."""

    group: SlotGroup
    ingredients: list[str]
    max_time: int | None = None

    def __str__(self) -> str:
        return f"{self.group.value}: {', '.join(self.ingredients[:3])} (max {self.max_time}min)"
