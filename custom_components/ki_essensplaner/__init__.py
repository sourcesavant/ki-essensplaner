"""KI-Essensplaner integration for Home Assistant."""

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv

from .const import CONF_API_TOKEN, CONF_API_URL, DOMAIN
from .coordinator import EssensplanerCoordinator

PLATFORMS: list[Platform] = [Platform.SENSOR]

# Service schemas
RATE_RECIPE_SCHEMA = vol.Schema({
    vol.Required("recipe_id"): cv.positive_int,
    vol.Required("rating"): vol.All(vol.Coerce(int), vol.Range(min=1, max=5)),
})

EXCLUDE_INGREDIENT_SCHEMA = vol.Schema({
    vol.Required("ingredient_name"): cv.string,
})

REMOVE_EXCLUSION_SCHEMA = vol.Schema({
    vol.Required("ingredient_name"): cv.string,
})


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up KI-Essensplaner from a config entry."""
    api_url = entry.data[CONF_API_URL]
    api_token = entry.data.get(CONF_API_TOKEN)

    coordinator = EssensplanerCoordinator(hass, api_url, api_token)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Register services (only once for the first entry)
    if len(hass.data[DOMAIN]) == 1:
        await async_setup_services(hass)

    return True


async def async_setup_services(hass: HomeAssistant) -> None:
    """Set up services for the integration."""

    async def handle_rate_recipe(call: ServiceCall) -> None:
        """Handle rate_recipe service call."""
        recipe_id = call.data["recipe_id"]
        rating = call.data["rating"]

        # Get the first available coordinator
        # In single-user setup, there's only one
        coordinator = next(iter(hass.data[DOMAIN].values()))
        await coordinator.rate_recipe(recipe_id, rating)

    async def handle_exclude_ingredient(call: ServiceCall) -> None:
        """Handle exclude_ingredient service call."""
        ingredient_name = call.data["ingredient_name"]

        coordinator = next(iter(hass.data[DOMAIN].values()))
        await coordinator.exclude_ingredient(ingredient_name)

    async def handle_remove_exclusion(call: ServiceCall) -> None:
        """Handle remove_ingredient_exclusion service call."""
        ingredient_name = call.data["ingredient_name"]

        coordinator = next(iter(hass.data[DOMAIN].values()))
        await coordinator.remove_ingredient_exclusion(ingredient_name)

    async def handle_refresh_profile(call: ServiceCall) -> None:
        """Handle refresh_profile service call."""
        coordinator = next(iter(hass.data[DOMAIN].values()))
        await coordinator.refresh_profile()

    # Register services
    hass.services.async_register(
        DOMAIN, "rate_recipe", handle_rate_recipe, schema=RATE_RECIPE_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, "exclude_ingredient", handle_exclude_ingredient, schema=EXCLUDE_INGREDIENT_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, "remove_ingredient_exclusion", handle_remove_exclusion, schema=REMOVE_EXCLUSION_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, "refresh_profile", handle_refresh_profile
    )


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)

        # Remove services if this was the last entry
        if not hass.data[DOMAIN]:
            hass.services.async_remove(DOMAIN, "rate_recipe")
            hass.services.async_remove(DOMAIN, "exclude_ingredient")
            hass.services.async_remove(DOMAIN, "remove_ingredient_exclusion")
            hass.services.async_remove(DOMAIN, "refresh_profile")

    return unload_ok
