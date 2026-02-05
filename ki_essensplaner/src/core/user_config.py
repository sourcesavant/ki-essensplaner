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
