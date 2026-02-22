"""User configuration management.

This module manages user-specific configuration like household size,
which is used to scale recipe quantities in shopping lists.

The configuration is stored in data/local/config.json.

Example usage:
    >>> from src.core.user_config import get_household_size, set_household_size
    >>> set_household_size(4)
    >>> size = get_household_size()  # Returns 4

Issue #30: Portionenanzahl & automatische Rezept-Skalierung
"""

import json
from datetime import datetime
from pathlib import Path

from src.core.config import LOCAL_DIR

CONFIG_PATH = LOCAL_DIR / "config.json"
DEFAULT_HOUSEHOLD_SIZE = 2
DEFAULT_ROTATION_POLICY = {
    "no_repeat_weeks": 1,
    "favorite_min_return_weeks": 3,
    "favorite_return_bonus_per_week": 2.0,
    "favorite_return_bonus_max": 10.0,
}


def _normalize_rotation_policy(policy: dict | None) -> dict:
    """Normalize a rotation policy dict with defaults and bounds."""
    raw = policy if isinstance(policy, dict) else {}

    merged = dict(DEFAULT_ROTATION_POLICY)
    merged.update(raw)

    try:
        no_repeat_weeks = int(merged["no_repeat_weeks"])
    except (TypeError, ValueError):
        no_repeat_weeks = DEFAULT_ROTATION_POLICY["no_repeat_weeks"]

    try:
        favorite_min_return_weeks = int(merged["favorite_min_return_weeks"])
    except (TypeError, ValueError):
        favorite_min_return_weeks = DEFAULT_ROTATION_POLICY["favorite_min_return_weeks"]

    try:
        bonus_per_week = float(merged["favorite_return_bonus_per_week"])
    except (TypeError, ValueError):
        bonus_per_week = DEFAULT_ROTATION_POLICY["favorite_return_bonus_per_week"]

    try:
        bonus_max = float(merged["favorite_return_bonus_max"])
    except (TypeError, ValueError):
        bonus_max = DEFAULT_ROTATION_POLICY["favorite_return_bonus_max"]

    return {
        "no_repeat_weeks": max(0, no_repeat_weeks),
        "favorite_min_return_weeks": max(0, favorite_min_return_weeks),
        "favorite_return_bonus_per_week": max(0.0, bonus_per_week),
        "favorite_return_bonus_max": max(0.0, bonus_max),
    }


def load_config() -> dict:
    """Load user configuration from file.

    Returns:
        Configuration dictionary with at least 'household_size' key
    """
    if not CONFIG_PATH.exists():
        return {"household_size": DEFAULT_HOUSEHOLD_SIZE}

    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {"household_size": DEFAULT_HOUSEHOLD_SIZE}


def save_config(config: dict) -> None:
    """Save user configuration to file.

    Args:
        config: Configuration dictionary to save
    """
    config["updated_at"] = datetime.now().isoformat()
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)

    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)


def get_household_size() -> int:
    """Get configured household size.

    Returns:
        Number of people in household (1-10)
    """
    return load_config().get("household_size", DEFAULT_HOUSEHOLD_SIZE)


def get_rotation_policy() -> dict:
    """Get recipe rotation policy for weekly plan generation.

    Returns:
        Dict with validated numeric rotation settings.
    """
    config = load_config()
    return _normalize_rotation_policy(config.get("rotation_policy"))


def get_multi_day_preferences() -> list[dict]:
    """Get stored multi-day meal prep preferences.

    Returns:
        List of preference groups (may be empty)
    """
    prefs = load_config().get("multi_day_preferences", [])
    if isinstance(prefs, list):
        return prefs
    return []


def set_multi_day_preferences(groups: list[dict]) -> None:
    """Set multi-day meal prep preferences.

    Args:
        groups: List of preference groups to persist
    """
    config = load_config()
    config["multi_day_preferences"] = groups
    save_config(config)


def get_skipped_slots() -> list[dict]:
    """Get stored skipped slots for plan generation.

    Returns:
        List of slots to skip (may be empty)
    """
    skipped = load_config().get("skipped_slots", [])
    if isinstance(skipped, list):
        return skipped
    return []


def set_skipped_slots(slots: list[dict]) -> None:
    """Set skipped slots for plan generation.

    Args:
        slots: List of {"weekday": "...", "slot": "..."} dicts
    """
    config = load_config()
    config["skipped_slots"] = slots
    save_config(config)


def set_household_size(size: int) -> None:
    """Set household size (1-10 persons).

    Args:
        size: Number of people in household

    Raises:
        ValueError: If size is not between 1 and 10
    """
    if not 1 <= size <= 10:
        raise ValueError("Haushaltsgröße muss zwischen 1 und 10 liegen")

    config = load_config()
    config["household_size"] = size
    save_config(config)


def set_rotation_policy(policy: dict) -> dict:
    """Set recipe rotation policy and return normalized values.

    Args:
        policy: Partial or complete rotation policy

    Returns:
        Normalized rotation policy that was persisted
    """
    normalized = _normalize_rotation_policy(policy)
    config = load_config()
    config["rotation_policy"] = normalized
    save_config(config)
    return normalized
