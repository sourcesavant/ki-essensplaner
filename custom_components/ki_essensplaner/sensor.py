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
    async_add_entities([EssensplanerApiStatusSensor(coordinator, entry)])


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
