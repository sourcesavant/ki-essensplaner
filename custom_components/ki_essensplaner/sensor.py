"""Sensor platform for KI-Essensplaner."""
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

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
        HouseholdSizeSensor(coordinator, entry),

        # Weekly plan status sensor
        WeeklyPlanStatusSensor(coordinator, entry),

        # Multi-day meal prep sensor
        MultiDayOverviewSensor(coordinator, entry),

        # Next meal sensor
        NextMealSensor(coordinator, entry),

        # Shopping list sensors
        ShoppingListCountSensor(coordinator, entry),
        BiolandCountSensor(coordinator, entry),
        ReweCountSensor(coordinator, entry),
    ]

    # Add 14 slot sensors (7 days x 2 meals)
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

    @property
    def native_value(self) -> int:
        """Return the number of ingredients in profile."""
        profile = self.coordinator.data.get("profile") if self.coordinator.data else None
        if profile is None:
            return 0

        ingredient_prefs = profile.get("ingredient_preferences", [])
        return len(ingredient_prefs)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        profile = self.coordinator.data.get("profile") if self.coordinator.data else None
        if profile is None:
            return {"ingredients": []}

        # Get top 10 ingredients
        ingredient_prefs = profile.get("ingredient_preferences", [])
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

    @property
    def native_value(self) -> int:
        """Return the number of excluded ingredients."""
        ingredients = self.coordinator.data.get("excluded_ingredients", []) if self.coordinator.data else []
        return len(ingredients)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        ingredients = self.coordinator.data.get("excluded_ingredients", []) if self.coordinator.data else []
        return {
            "ingredients": sorted(ingredients),
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

    @property
    def native_value(self) -> str:
        """Return the state of the sensor."""
        plan = self.coordinator.data.get("weekly_plan") if self.coordinator.data else None
        if plan is None:
            return "no_plan"
        return "active"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        plan = self.coordinator.data.get("weekly_plan") if self.coordinator.data else None
        if plan is None:
            return {}

        return {
            "week_start": plan.get("week_start"),
            "generated_at": plan.get("generated_at"),
            "favorites_count": plan.get("favorites_count", 0),
            "new_count": plan.get("new_count", 0),
            "total_slots": len(plan.get("slots", [])),
        }


class WeeklyPlanSlotSensor(CoordinatorEntity[EssensplanerCoordinator], SensorEntity):
    """Sensor for a single meal slot in weekly plan."""

    _attr_has_entity_name = True

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

    def _get_slot_data(self) -> dict[str, Any] | None:
        """Get slot data from plan."""
        plan = self.coordinator.data.get("weekly_plan") if self.coordinator.data else None
        if plan is None:
            return None

        for slot in plan.get("slots", []):
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

        attrs = {
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
            # Multi-day attributes
            "is_reuse_slot": slot_data.get("is_reuse_slot", False),
            "prep_days": slot_data.get("prep_days", 1),
        }

        # Reuse info
        if slot_data.get("reuse_from"):
            attrs["reuse_from_weekday"] = slot_data["reuse_from"]["weekday"]
            attrs["reuse_from_slot"] = slot_data["reuse_from"]["slot"]
            attrs["cook_day"] = slot_data["reuse_from"]["weekday"]

        return attrs

    @property
    def icon(self) -> str:
        """Return icon based on slot type."""
        slot_data = self._get_slot_data()
        if slot_data and slot_data.get("is_reuse_slot"):
            return "mdi:food-takeout-box"  # Leftovers icon
        return "mdi:silverware-fork-knife"


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

    def _get_next_meal_slot(self) -> tuple[str, str] | None:
        """Determine next meal slot based on current time."""
        now = dt_util.now()
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
        plan = self.coordinator.data.get("weekly_plan") if self.coordinator.data else None
        if plan is None:
            return None

        for s in plan.get("slots", []):
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


class HouseholdSizeSensor(CoordinatorEntity[EssensplanerCoordinator], SensorEntity):
    """Sensor for household size configuration."""

    _attr_has_entity_name = True
    _attr_name = "Household Size"
    _attr_icon = "mdi:account-group"
    _attr_native_unit_of_measurement = "Personen"

    def __init__(
        self,
        coordinator: EssensplanerCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_household_size"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
        }

    @property
    def native_value(self) -> int:
        """Return household size."""
        config = self.coordinator.data.get("config") if self.coordinator.data else None
        if config is None:
            return 2
        return config.get("household_size", 2)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        config = self.coordinator.data.get("config") if self.coordinator.data else None
        if config is None:
            return {}

        return {
            "updated_at": config.get("updated_at"),
        }


class MultiDayOverviewSensor(CoordinatorEntity[EssensplanerCoordinator], SensorEntity):
    """Sensor showing multi-day meal prep overview."""

    _attr_has_entity_name = True
    _attr_name = "Vorkochen"
    _attr_icon = "mdi:pot-steam"

    def __init__(
        self,
        coordinator: EssensplanerCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_multi_day_overview"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
        }

    @property
    def native_value(self) -> str:
        """Return number of multi-day groups."""
        groups = self.coordinator.data.get("multi_day_groups", []) if self.coordinator.data else []
        if not groups:
            return "Kein Vorkochen"
        return f"{len(groups)} Gerichte"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return multi-day details."""
        groups = self.coordinator.data.get("multi_day_groups", []) if self.coordinator.data else []
        return {
            "groups": groups,
            "total_prep_meals": sum(g.get("total_days", 1) for g in groups),
            "unique_recipes": len(groups),
        }


class ShoppingListCountSensor(CoordinatorEntity[EssensplanerCoordinator], SensorEntity):
    """Sensor for total shopping list item count."""

    _attr_has_entity_name = True
    _attr_name = "Einkaufsliste Anzahl"
    _attr_icon = "mdi:cart"
    _attr_native_unit_of_measurement = "Positionen"

    def __init__(
        self,
        coordinator: EssensplanerCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_shopping_list_count"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
        }

    @property
    def native_value(self) -> int:
        """Return the total number of shopping list items."""
        shopping_list = self.coordinator.data.get("shopping_list") if self.coordinator.data else None
        if shopping_list is None:
            return 0
        return len(shopping_list.get("items", []))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        shopping_list = self.coordinator.data.get("shopping_list") if self.coordinator.data else None
        if shopping_list is None:
            return {
                "week_start": None,
                "recipe_count": 0,
                "household_size": 2,
                "items": [],
            }

        return {
            "week_start": shopping_list.get("week_start"),
            "recipe_count": shopping_list.get("recipe_count", 0),
            "household_size": shopping_list.get("household_size", 2),
            "items": shopping_list.get("items", []),
        }


class BiolandCountSensor(CoordinatorEntity[EssensplanerCoordinator], SensorEntity):
    """Sensor for Bioland shopping list item count."""

    _attr_has_entity_name = True
    _attr_name = "Bioland Anzahl"
    _attr_icon = "mdi:cart"
    _attr_native_unit_of_measurement = "Positionen"

    def __init__(
        self,
        coordinator: EssensplanerCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_bioland_count"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
        }

    @property
    def native_value(self) -> int:
        """Return the number of Bioland items."""
        split = self.coordinator.data.get("split_shopping_list") if self.coordinator.data else None
        if split is None:
            return 0
        return len(split.get("bioland", []))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        split = self.coordinator.data.get("split_shopping_list") if self.coordinator.data else None
        if split is None:
            return {
                "items": [],
                "week_start": None,
            }

        return {
            "items": split.get("bioland", []),
            "week_start": split.get("week_start"),
        }


class ReweCountSensor(CoordinatorEntity[EssensplanerCoordinator], SensorEntity):
    """Sensor for Rewe shopping list item count."""

    _attr_has_entity_name = True
    _attr_name = "Rewe Anzahl"
    _attr_icon = "mdi:cart"
    _attr_native_unit_of_measurement = "Positionen"

    def __init__(
        self,
        coordinator: EssensplanerCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_rewe_count"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
        }

    @property
    def native_value(self) -> int:
        """Return the number of Rewe items."""
        split = self.coordinator.data.get("split_shopping_list") if self.coordinator.data else None
        if split is None:
            return 0
        return len(split.get("rewe", []))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        split = self.coordinator.data.get("split_shopping_list") if self.coordinator.data else None
        if split is None:
            return {
                "items": [],
                "week_start": None,
            }

        return {
            "items": split.get("rewe", []),
            "week_start": split.get("week_start"),
        }
