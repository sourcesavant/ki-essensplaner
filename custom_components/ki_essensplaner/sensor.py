"""Sensor platform for KI-Essensplaner."""

from datetime import datetime, timedelta
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
    DINNER_TIME,
    DOMAIN,
    LUNCH_TIME,
    MEAL_SLOTS,
    STATE_OFFLINE,
    WEEKDAY_MAP,
)
from .coordinator import EssensplanerCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensors from a config entry."""
    coordinator: EssensplanerCoordinator = hass.data[DOMAIN][entry.entry_id]

    sensors = [
        # Status sensors
        EssensplanerApiStatusSensor(coordinator, entry),
        EssensplanerProfileStatusSensor(coordinator, entry),
        EssensplanerTopIngredientsSensor(coordinator, entry),
        EssensplanerExcludedIngredientsSensor(coordinator, entry),

        # Weekly plan status sensor
        WeeklyPlanStatusSensor(coordinator, entry),

        # Next meal sensor
        NextMealSensor(coordinator, entry),
    ]

    # Add 14 slot sensors (7 days × 2 meals)
    for weekday in WEEKDAY_MAP.values():
        for slot in MEAL_SLOTS:
            sensors.append(WeeklyPlanSlotSensor(coordinator, entry, weekday, slot))

    async_add_entities(sensors)


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


class WeeklyPlanStatusSensor(CoordinatorEntity[EssensplanerCoordinator], SensorEntity):
    """Sensor for overall weekly plan status."""

    _attr_has_entity_name = True
    _attr_name = "Weekly Plan Status"
    _attr_icon = "mdi:calendar-week"

    def __init__(
        self,
        coordinator: EssensplanerCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_weekly_plan_status"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
        }
        self._plan_data: dict[str, Any] | None = None

    async def async_update(self) -> None:
        """Update the sensor."""
        await super().async_update()
        self._plan_data = await self.coordinator.get_weekly_plan()

    @property
    def native_value(self) -> str:
        """Return the state of the sensor."""
        if self._plan_data is None:
            return "no_plan"
        return "active"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        if self._plan_data is None:
            return {}

        return {
            "week_start": self._plan_data.get("week_start"),
            "generated_at": self._plan_data.get("generated_at"),
            "favorites_count": self._plan_data.get("favorites_count", 0),
            "new_count": self._plan_data.get("new_count", 0),
            "total_slots": len(self._plan_data.get("slots", [])),
        }


class WeeklyPlanSlotSensor(CoordinatorEntity[EssensplanerCoordinator], SensorEntity):
    """Sensor for a single meal slot in weekly plan."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:food"

    def __init__(
        self,
        coordinator: EssensplanerCoordinator,
        entry: ConfigEntry,
        weekday: str,
        slot: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._weekday = weekday
        self._slot = slot
        self._attr_name = f"{weekday} {slot}"
        # Create a safe unique_id with lowercase and underscores
        safe_weekday = weekday.lower().replace("ä", "ae").replace("ö", "oe").replace("ü", "ue")
        safe_slot = slot.lower()
        self._attr_unique_id = f"{entry.entry_id}_{safe_weekday}_{safe_slot}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
        }
        self._plan_data: dict[str, Any] | None = None

    async def async_update(self) -> None:
        """Update the sensor."""
        await super().async_update()
        self._plan_data = await self.coordinator.get_weekly_plan()

    def _get_slot_data(self) -> dict[str, Any] | None:
        """Get slot data from plan."""
        if self._plan_data is None:
            return None

        for slot in self._plan_data.get("slots", []):
            if slot.get("weekday") == self._weekday and slot.get("slot") == self._slot:
                return slot
        return None

    @property
    def native_value(self) -> str:
        """Return the state of the sensor."""
        slot_data = self._get_slot_data()
        if slot_data is None:
            return "Kein Plan"

        recommendations = slot_data.get("recommendations", [])
        selected_index = slot_data.get("selected_index", 0)

        if not recommendations or selected_index >= len(recommendations):
            return "Kein Plan"

        selected_recipe = recommendations[selected_index]
        return selected_recipe.get("title", "Unbekannt")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        slot_data = self._get_slot_data()
        if slot_data is None:
            return {
                "weekday": self._weekday,
                "slot": self._slot,
            }

        recommendations = slot_data.get("recommendations", [])
        selected_index = slot_data.get("selected_index", 0)

        if not recommendations or selected_index >= len(recommendations):
            return {
                "weekday": self._weekday,
                "slot": self._slot,
            }

        selected_recipe = recommendations[selected_index]

        return {
            "weekday": self._weekday,
            "slot": self._slot,
            "recipe_id": selected_recipe.get("recipe_id"),
            "recipe_url": selected_recipe.get("url"),
            "prep_time_minutes": selected_recipe.get("prep_time_minutes"),
            "calories": selected_recipe.get("calories"),
            "score": selected_recipe.get("score"),
            "is_new": selected_recipe.get("is_new"),
            "alternatives": len(recommendations) - 1,
            "selected_index": selected_index,
            "ingredients": selected_recipe.get("ingredients", []),
        }


class NextMealSensor(CoordinatorEntity[EssensplanerCoordinator], SensorEntity):
    """Sensor for the next upcoming meal."""

    _attr_has_entity_name = True
    _attr_name = "Next Meal"
    _attr_icon = "mdi:clock-outline"

    def __init__(
        self,
        coordinator: EssensplanerCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_next_meal"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
        }
        self._plan_data: dict[str, Any] | None = None

    async def async_update(self) -> None:
        """Update the sensor."""
        await super().async_update()
        self._plan_data = await self.coordinator.get_weekly_plan()

    def _get_next_meal_slot(self) -> tuple[str, str] | None:
        """Determine next meal slot based on current time."""
        now = datetime.now()
        current_time = now.hour * 60 + now.minute
        current_weekday = now.weekday()

        lunch_time = LUNCH_TIME[0] * 60 + LUNCH_TIME[1]
        dinner_time = DINNER_TIME[0] * 60 + DINNER_TIME[1]

        if current_time < lunch_time:
            # Before lunch -> today's lunch
            return WEEKDAY_MAP[current_weekday], "Mittagessen"
        elif current_time < dinner_time:
            # After lunch, before dinner -> today's dinner
            return WEEKDAY_MAP[current_weekday], "Abendessen"
        else:
            # After dinner -> tomorrow's lunch
            tomorrow = (current_weekday + 1) % 7
            return WEEKDAY_MAP[tomorrow], "Mittagessen"

    def _get_slot_data(self, weekday: str, slot: str) -> dict[str, Any] | None:
        """Get slot data from plan."""
        if self._plan_data is None:
            return None

        for s in self._plan_data.get("slots", []):
            if s.get("weekday") == weekday and s.get("slot") == slot:
                return s
        return None

    @property
    def native_value(self) -> str:
        """Return the state of the sensor."""
        next_slot = self._get_next_meal_slot()
        if next_slot is None:
            return "Keine Mahlzeit geplant"

        weekday, slot = next_slot
        slot_data = self._get_slot_data(weekday, slot)

        if slot_data is None:
            return "Keine Mahlzeit geplant"

        recommendations = slot_data.get("recommendations", [])
        selected_index = slot_data.get("selected_index", 0)

        if not recommendations or selected_index >= len(recommendations):
            return "Keine Mahlzeit geplant"

        selected_recipe = recommendations[selected_index]
        return selected_recipe.get("title", "Unbekannt")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        next_slot = self._get_next_meal_slot()
        if next_slot is None:
            return {}

        weekday, slot = next_slot
        slot_data = self._get_slot_data(weekday, slot)

        if slot_data is None:
            return {
                "next_weekday": weekday,
                "next_slot": slot,
            }

        recommendations = slot_data.get("recommendations", [])
        selected_index = slot_data.get("selected_index", 0)

        if not recommendations or selected_index >= len(recommendations):
            return {
                "next_weekday": weekday,
                "next_slot": slot,
            }

        selected_recipe = recommendations[selected_index]

        return {
            "next_weekday": weekday,
            "next_slot": slot,
            "recipe_id": selected_recipe.get("recipe_id"),
            "recipe_url": selected_recipe.get("url"),
            "prep_time_minutes": selected_recipe.get("prep_time_minutes"),
            "calories": selected_recipe.get("calories"),
            "ingredients": selected_recipe.get("ingredients", []),
        }
