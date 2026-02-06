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

SELECT_RECIPE_SCHEMA = vol.Schema({
    vol.Required("weekday"): cv.string,
    vol.Required("slot"): cv.string,
    vol.Required("recipe_index"): vol.All(vol.Coerce(int), vol.Range(min=0, max=4)),
})

SET_HOUSEHOLD_SIZE_SCHEMA = vol.Schema({
    vol.Required("size"): vol.All(vol.Coerce(int), vol.Range(min=1, max=10)),
})

SET_MULTI_DAY_SCHEMA = vol.Schema({
    vol.Required("primary_weekday"): cv.string,
    vol.Required("primary_slot"): cv.string,
    vol.Required("reuse_days"): vol.All(vol.Coerce(int), vol.Range(min=1, max=3)),
})

CLEAR_MULTI_DAY_PREFERENCES_SCHEMA = vol.Schema({
    vol.Optional("primary_weekday"): cv.string,
    vol.Optional("primary_slot"): cv.string,
})

SET_MULTI_DAY_PREFERENCES_SCHEMA = vol.Schema({
    vol.Required("primary_weekday"): cv.string,
    vol.Required("primary_slot"): cv.string,
    vol.Required("reuse_days"): vol.All(vol.Coerce(int), vol.Range(min=1, max=6)),
})

CLEAR_MULTI_DAY_SCHEMA = vol.Schema({
    vol.Required("weekday"): cv.string,
    vol.Required("slot"): cv.string,
})

FETCH_RECIPES_SCHEMA = vol.Schema({
    vol.Optional("delay_seconds", default=0.5): vol.Coerce(float),
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

        # Fire event
        hass.bus.async_fire(
            f"{DOMAIN}_profile_updated",
            {"message": "Preference profile has been refreshed"},
        )

    async def handle_generate_weekly_plan(call: ServiceCall) -> None:
        """Handle generate_weekly_plan service call."""
        coordinator = next(iter(hass.data[DOMAIN].values()))
        await coordinator.generate_weekly_plan()

        # Fire events
        hass.bus.async_fire(
            f"{DOMAIN}_plan_generated",
            {"message": "New weekly plan has been generated"},
        )
        hass.bus.async_fire(
            f"{DOMAIN}_shopping_list_ready",
            {"message": "Weekly plan generated, shopping list is now available"},
        )

        # Send persistent notification
        await hass.services.async_call(
            "persistent_notification",
            "create",
            {
                "title": "Wochenplan erstellt",
                "message": "Ein neuer Wochenplan wurde generiert. Die Einkaufsliste ist jetzt verfügbar.",
                "notification_id": f"{DOMAIN}_plan_generated",
            },
            blocking=False,
        )

    async def handle_select_recipe(call: ServiceCall) -> None:
        """Handle select_recipe service call."""
        weekday = call.data["weekday"]
        slot = call.data["slot"]
        recipe_index = call.data["recipe_index"]

        coordinator = next(iter(hass.data[DOMAIN].values()))
        await coordinator.select_recipe(weekday, slot, recipe_index)

        # Fire event
        hass.bus.async_fire(
            f"{DOMAIN}_plan_updated",
            {
                "message": f"Recipe selection changed for {weekday} {slot}",
                "weekday": weekday,
                "slot": slot,
                "recipe_index": recipe_index,
            },
        )

    async def handle_delete_weekly_plan(call: ServiceCall) -> None:
        """Handle delete_weekly_plan service call."""
        coordinator = next(iter(hass.data[DOMAIN].values()))
        await coordinator.delete_weekly_plan()

    async def handle_set_household_size(call: ServiceCall) -> None:
        """Handle set_household_size service call."""
        size = call.data["size"]
        coordinator = next(iter(hass.data[DOMAIN].values()))
        await coordinator.set_household_size(size)

    async def handle_set_multi_day(call: ServiceCall) -> None:
        """Handle set_multi_day service call."""
        primary_weekday = call.data["primary_weekday"]
        primary_slot = call.data["primary_slot"]
        reuse_days = call.data["reuse_days"]

        # Calculate reuse slots based on consecutive days
        weekdays = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]
        start_idx = weekdays.index(primary_weekday)
        reuse_slots = []

        for i in range(1, reuse_days + 1):
            next_idx = (start_idx + i) % 7
            reuse_slots.append({
                "weekday": weekdays[next_idx],
                "slot": primary_slot
            })

        coordinator = next(iter(hass.data[DOMAIN].values()))
        await coordinator.set_multi_day(primary_weekday, primary_slot, reuse_slots)

    async def handle_set_multi_day_preferences(call: ServiceCall) -> None:
        """Handle set_multi_day_preferences service call."""
        primary_weekday = call.data["primary_weekday"]
        primary_slot = call.data["primary_slot"]
        reuse_days = call.data["reuse_days"]

        weekdays = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]
        start_idx = weekdays.index(primary_weekday)
        reuse_slots = []

        for i in range(1, reuse_days + 1):
            next_idx = (start_idx + i) % 7
            reuse_slots.append({
                "weekday": weekdays[next_idx],
                "slot": primary_slot
            })

        coordinator = next(iter(hass.data[DOMAIN].values()))
        existing = await coordinator.get_multi_day_preferences()
        updated = [
            g for g in existing
            if not (
                g.get("primary_weekday") == primary_weekday
                and g.get("primary_slot") == primary_slot
            )
        ]
        updated.append({
            "primary_weekday": primary_weekday,
            "primary_slot": primary_slot,
            "reuse_slots": reuse_slots,
        })
        await coordinator.set_multi_day_preferences(updated)

    async def handle_clear_multi_day_preferences(call: ServiceCall) -> None:
        """Handle clear_multi_day_preferences service call."""
        primary_weekday = call.data.get("primary_weekday")
        primary_slot = call.data.get("primary_slot")

        coordinator = next(iter(hass.data[DOMAIN].values()))
        if not primary_weekday or not primary_slot:
            await coordinator.set_multi_day_preferences([])
            return

        existing = await coordinator.get_multi_day_preferences()
        updated = [
            g for g in existing
            if not (
                g.get("primary_weekday") == primary_weekday
                and g.get("primary_slot") == primary_slot
            )
        ]
        await coordinator.set_multi_day_preferences(updated)

    async def handle_clear_multi_day(call: ServiceCall) -> None:
        """Handle clear_multi_day service call."""
        weekday = call.data["weekday"]
        slot = call.data["slot"]

        coordinator = next(iter(hass.data[DOMAIN].values()))
        await coordinator.clear_multi_day(weekday, slot)

    async def handle_fetch_recipes(call: ServiceCall) -> None:
        """Handle fetch_recipes service call."""
        delay_seconds = call.data.get("delay_seconds", 0.5)
        coordinator = next(iter(hass.data[DOMAIN].values()))
        await coordinator.fetch_recipes(delay_seconds)

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
    hass.services.async_register(
        DOMAIN, "generate_weekly_plan", handle_generate_weekly_plan
    )
    hass.services.async_register(
        DOMAIN, "select_recipe", handle_select_recipe, schema=SELECT_RECIPE_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, "delete_weekly_plan", handle_delete_weekly_plan
    )
    hass.services.async_register(
        DOMAIN, "set_household_size", handle_set_household_size, schema=SET_HOUSEHOLD_SIZE_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, "set_multi_day", handle_set_multi_day, schema=SET_MULTI_DAY_SCHEMA
    )
    hass.services.async_register(
        DOMAIN,
        "set_multi_day_preferences",
        handle_set_multi_day_preferences,
        schema=SET_MULTI_DAY_PREFERENCES_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        "clear_multi_day_preferences",
        handle_clear_multi_day_preferences,
        schema=CLEAR_MULTI_DAY_PREFERENCES_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN, "clear_multi_day", handle_clear_multi_day, schema=CLEAR_MULTI_DAY_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, "fetch_recipes", handle_fetch_recipes, schema=FETCH_RECIPES_SCHEMA
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
            hass.services.async_remove(DOMAIN, "generate_weekly_plan")
            hass.services.async_remove(DOMAIN, "select_recipe")
            hass.services.async_remove(DOMAIN, "delete_weekly_plan")
            hass.services.async_remove(DOMAIN, "set_household_size")
            hass.services.async_remove(DOMAIN, "set_multi_day")
            hass.services.async_remove(DOMAIN, "clear_multi_day")
            hass.services.async_remove(DOMAIN, "set_multi_day_preferences")
            hass.services.async_remove(DOMAIN, "clear_multi_day_preferences")
            hass.services.async_remove(DOMAIN, "fetch_recipes")

    return unload_ok
