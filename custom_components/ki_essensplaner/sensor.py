"""Sensor platform for KI-Essensplaner."""

from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    ATTR_BIOLAND_AGE_DAYS,
    ATTR_CACHED,
    ATTR_DATABASE_OK,
    ATTR_PROFILE_AGE_DAYS,
    DOMAIN,
    STATE_OFFLINE,
)
from .coordinator import EssensplanerCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensors from a config entry."""
    coordinator: EssensplanerCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([
        EssensplanerApiStatusSensor(coordinator, entry),
        EssensplanerProfileStatusSensor(coordinator, entry),
        EssensplanerTopIngredientsSensor(coordinator, entry),
        EssensplanerExcludedIngredientsSensor(coordinator, entry),
    ])


class EssensplanerApiStatusSensor(CoordinatorEntity[EssensplanerCoordinator], SensorEntity):
    """Sensor for KI-Essensplaner API status."""

    _attr_has_entity_name = True
    _attr_name = "API Status"
    _attr_icon = "mdi:food"

    def __init__(
        self,
        coordinator: EssensplanerCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_api_status"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": "KI-Essensplaner",
            "manufacturer": "sourcesavant",
            "model": "Essensplaner API",
        }

    @property
    def native_value(self) -> str:
        """Return the state of the sensor."""
        if self.coordinator.data is None:
            return STATE_OFFLINE
        return self.coordinator.data.get("status", STATE_OFFLINE)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        if self.coordinator.data is None:
            return {
                ATTR_DATABASE_OK: False,
                ATTR_PROFILE_AGE_DAYS: None,
                ATTR_BIOLAND_AGE_DAYS: None,
                ATTR_CACHED: False,
            }

        return {
            ATTR_DATABASE_OK: self.coordinator.data.get("database_ok", False),
            ATTR_PROFILE_AGE_DAYS: self.coordinator.data.get("profile_age_days"),
            ATTR_BIOLAND_AGE_DAYS: self.coordinator.data.get("bioland_age_days"),
            ATTR_CACHED: self.coordinator.data.get("cached", False),
        }


class EssensplanerProfileStatusSensor(CoordinatorEntity[EssensplanerCoordinator], SensorEntity):
    """Sensor for preference profile status."""

    _attr_has_entity_name = True
    _attr_name = "Profile Status"
    _attr_icon = "mdi:account-heart"

    def __init__(
        self,
        coordinator: EssensplanerCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_profile_status"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
        }

    @property
    def native_value(self) -> str:
        """Return the state of the sensor."""
        if self.coordinator.data is None:
            return "unknown"

        profile_age = self.coordinator.data.get(ATTR_PROFILE_AGE_DAYS)
        if profile_age is None:
            return "missing"
        elif profile_age > 7:
            return "outdated"
        return "current"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        if self.coordinator.data is None:
            return {}

        profile_age = self.coordinator.data.get(ATTR_PROFILE_AGE_DAYS)
        return {
            "profile_age_days": profile_age,
            "needs_update": profile_age is not None and profile_age > 7,
        }


class EssensplanerTopIngredientsSensor(CoordinatorEntity[EssensplanerCoordinator], SensorEntity):
    """Sensor for top favorite ingredients."""

    _attr_has_entity_name = True
    _attr_name = "Top Ingredients"
    _attr_icon = "mdi:star"

    def __init__(
        self,
        coordinator: EssensplanerCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_top_ingredients"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
        }
        self._profile_data: dict[str, Any] | None = None

    async def async_update(self) -> None:
        """Update the sensor by fetching profile data."""
        await super().async_update()
        # Fetch full profile data for top ingredients
        self._profile_data = await self.coordinator.get_profile()

    @property
    def native_value(self) -> int:
        """Return the number of ingredients in profile."""
        if self._profile_data is None:
            return 0

        ingredient_prefs = self._profile_data.get("ingredient_preferences", [])
        return len(ingredient_prefs)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        if self._profile_data is None:
            return {"ingredients": []}

        # Get top 10 ingredients
        ingredient_prefs = self._profile_data.get("ingredient_preferences", [])
        top_10 = ingredient_prefs[:10]

        return {
            "ingredients": [
                {"name": ing.get("ingredient", ""), "score": ing.get("score", 0)}
                for ing in top_10
            ],
        }


class EssensplanerExcludedIngredientsSensor(CoordinatorEntity[EssensplanerCoordinator], SensorEntity):
    """Sensor for excluded ingredients."""

    _attr_has_entity_name = True
    _attr_name = "Excluded Ingredients"
    _attr_icon = "mdi:cancel"

    def __init__(
        self,
        coordinator: EssensplanerCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_excluded_ingredients"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
        }
        self._excluded_ingredients: list[str] = []

    async def async_update(self) -> None:
        """Update the sensor by fetching excluded ingredients."""
        await super().async_update()
        # Fetch excluded ingredients list
        self._excluded_ingredients = await self.coordinator.get_excluded_ingredients()

    @property
    def native_value(self) -> int:
        """Return the number of excluded ingredients."""
        return len(self._excluded_ingredients)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        return {
            "ingredients": sorted(self._excluded_ingredients),
        }
