"""DataUpdateCoordinator for KI-Essensplaner."""

from datetime import timedelta
import logging
from typing import Any

import aiohttp

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DEFAULT_SCAN_INTERVAL, STATE_OFFLINE

_LOGGER = logging.getLogger(__name__)


class EssensplanerCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator to fetch data from KI-Essensplaner API."""

    def __init__(
        self,
        hass: HomeAssistant,
        api_url: str,
        api_token: str | None = None,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name="KI-Essensplaner",
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
        )
        self.api_url = api_url.rstrip("/")
        self.api_token = api_token
        self._last_valid_data: dict[str, Any] | None = None
        self._cache: dict[str, Any] = {}

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from API with offline caching support."""
        try:
            async with aiohttp.ClientSession() as session:
                data = await self._fetch_health(session)

                data["profile"] = await self._fetch_cached_json(
                    session,
                    "profile",
                    "GET",
                    "/api/profile",
                )
                excluded = await self._fetch_cached_json(
                    session,
                    "excluded_ingredients",
                    "GET",
                    "/api/ingredients/excluded",
                )
                if isinstance(excluded, dict):
                    excluded = excluded.get("ingredients", [])
                data["excluded_ingredients"] = excluded or []
                data["weekly_plan"] = await self._fetch_cached_json(
                    session,
                    "weekly_plan",
                    "GET",
                    "/api/weekly-plan",
                    not_found_none=True,
                )
                data["config"] = await self._fetch_cached_json(
                    session,
                    "config",
                    "GET",
                    "/api/config",
                )
                data["multi_day_groups"] = await self._fetch_cached_json(
                    session,
                    "multi_day_groups",
                    "GET",
                    "/api/weekly-plan/multi-day",
                ) or []
                data["multi_day_preferences"] = await self._fetch_cached_json(
                    session,
                    "multi_day_preferences",
                    "GET",
                    "/api/weekly-plan/multi-day/preferences",
                ) or []
                prefs = data.get("multi_day_preferences")
                if isinstance(prefs, dict):
                    data["multi_day_preferences"] = prefs.get("groups", [])
                data["skipped_slots"] = await self._fetch_cached_json(
                    session,
                    "skipped_slots",
                    "GET",
                    "/api/weekly-plan/skip-slots",
                ) or []
                skipped = data.get("skipped_slots")
                if isinstance(skipped, dict):
                    data["skipped_slots"] = skipped.get("slots", [])
                data["shopping_list"] = await self._fetch_cached_json(
                    session,
                    "shopping_list",
                    "GET",
                    "/api/shopping-list",
                    not_found_none=True,
                )
                data["split_shopping_list"] = await self._fetch_cached_json(
                    session,
                    "split_shopping_list",
                    "GET",
                    "/api/shopping-list/split",
                    not_found_none=True,
                )

                return data

        except aiohttp.ClientError as err:
            _LOGGER.error("Error connecting to API: %s", err)
            # Return cached data if available, otherwise raise
            if self._last_valid_data is not None:
                cached = self._last_valid_data.copy()
                cached["cached"] = True
                _LOGGER.info("Using cached data due to connection error")
                return self._merge_cached_extras(cached)
            raise UpdateFailed(f"Error connecting to API: {err}") from err
        except Exception as err:
            _LOGGER.error("Unexpected error: %s", err)
            # Return cached data if available, otherwise raise
            if self._last_valid_data is not None:
                cached = self._last_valid_data.copy()
                cached["cached"] = True
                _LOGGER.info("Using cached data due to unexpected error")
                return self._merge_cached_extras(cached)
            raise UpdateFailed(f"Unexpected error: {err}") from err

    def _get_headers(self) -> dict[str, str]:
        """Get headers for API requests."""
        headers = {"Content-Type": "application/json"}
        if self.api_token:
            headers["Authorization"] = f"Bearer {self.api_token}"
        return headers

    async def _fetch_health(self, session: aiohttp.ClientSession) -> dict[str, Any]:
        """Fetch health data with offline caching support."""
        headers = {}
        if self.api_token:
            headers["Authorization"] = f"Bearer {self.api_token}"

        async with session.get(
            f"{self.api_url}/api/health",
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=10),
        ) as response:
            if response.status == 200:
                data = await response.json()
                # Cache valid data for offline fallback
                if data.get("status") != STATE_OFFLINE:
                    self._last_valid_data = data
                return data

            _LOGGER.warning(
                "API returned status %s: %s",
                response.status,
                await response.text(),
            )

            # Return cached data if available
            if self._last_valid_data is not None:
                cached = self._last_valid_data.copy()
                cached["cached"] = True
                _LOGGER.info("Using cached data due to API error")
                return cached

            return {
                "status": STATE_OFFLINE,
                "database_ok": False,
                "profile_age_days": None,
                "bioland_age_days": None,
                "cached": False,
            }

    async def _fetch_cached_json(
        self,
        session: aiohttp.ClientSession,
        cache_key: str,
        method: str,
        path: str,
        *,
        not_found_none: bool = False,
        timeout: int = 10,
    ) -> Any | None:
        """Fetch JSON with caching fallback on errors."""
        try:
            async with session.request(
                method,
                f"{self.api_url}{path}",
                headers=self._get_headers(),
                timeout=aiohttp.ClientTimeout(total=timeout),
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    self._cache[cache_key] = data
                    return data
                if not_found_none and response.status == 404:
                    self._cache[cache_key] = None
                    return None

                _LOGGER.warning(
                    "Failed to fetch %s (%s): %s",
                    cache_key,
                    response.status,
                    await response.text(),
                )
        except Exception as err:
            _LOGGER.error("Error fetching %s: %s", cache_key, err)

        return self._cache.get(cache_key)

    def _merge_cached_extras(self, data: dict[str, Any]) -> dict[str, Any]:
        """Merge cached extra payloads into the health data."""
        merged = data.copy()
        for key, value in self._cache.items():
            merged.setdefault(key, value)
        return merged

    async def rate_recipe(self, recipe_id: int, rating: int) -> None:
        """Rate a recipe via API.

        Args:
            recipe_id: The database ID of the recipe
            rating: Rating from 1 to 5 stars
        """
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.api_url}/api/recipes/{recipe_id}/rate",
                    headers=self._get_headers(),
                    json={"rating": rating},
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        _LOGGER.error("Failed to rate recipe: %s", error_text)
                        raise UpdateFailed(f"Failed to rate recipe: {error_text}")
        except aiohttp.ClientError as err:
            _LOGGER.error("Error rating recipe: %s", err)
            raise UpdateFailed(f"Error rating recipe: {err}") from err

    async def exclude_ingredient(self, ingredient_name: str) -> None:
        """Exclude an ingredient via API.

        Args:
            ingredient_name: Name of the ingredient to exclude
        """
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.api_url}/api/ingredients/exclude",
                    headers=self._get_headers(),
                    json={"ingredient_name": ingredient_name},
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        _LOGGER.error("Failed to exclude ingredient: %s", error_text)
                        raise UpdateFailed(f"Failed to exclude ingredient: {error_text}")
        except aiohttp.ClientError as err:
            _LOGGER.error("Error excluding ingredient: %s", err)
            raise UpdateFailed(f"Error excluding ingredient: {err}") from err

    async def remove_ingredient_exclusion(self, ingredient_name: str) -> None:
        """Remove ingredient exclusion via API.

        Args:
            ingredient_name: Name of the ingredient to remove from exclusions
        """
        try:
            async with aiohttp.ClientSession() as session:
                async with session.delete(
                    f"{self.api_url}/api/ingredients/exclude/{ingredient_name}",
                    headers=self._get_headers(),
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as response:
                    if response.status != 204:
                        error_text = await response.text()
                        _LOGGER.error("Failed to remove ingredient exclusion: %s", error_text)
                        raise UpdateFailed(f"Failed to remove ingredient exclusion: {error_text}")
        except aiohttp.ClientError as err:
            _LOGGER.error("Error removing ingredient exclusion: %s", err)
            raise UpdateFailed(f"Error removing ingredient exclusion: {err}") from err

    async def refresh_profile(self) -> None:
        """Refresh the preference profile via API."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.api_url}/api/profile/refresh",
                    headers=self._get_headers(),
                    timeout=aiohttp.ClientTimeout(total=60),
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        _LOGGER.error("Failed to refresh profile: %s", error_text)
                        raise UpdateFailed(f"Failed to refresh profile: {error_text}")
            # Refresh coordinator data after profile update
            await self.async_request_refresh()
        except aiohttp.ClientError as err:
            _LOGGER.error("Error refreshing profile: %s", err)
            raise UpdateFailed(f"Error refreshing profile: {err}") from err

    async def get_profile(self) -> dict[str, Any] | None:
        """Get the full profile data from API."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.api_url}/api/profile",
                    headers=self._get_headers(),
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as response:
                    if response.status == 200:
                        return await response.json()
                    return None
        except Exception as err:
            _LOGGER.error("Error fetching profile: %s", err)
            return None

    async def get_excluded_ingredients(self) -> list[str]:
        """Get list of excluded ingredients from API."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.api_url}/api/ingredients/excluded",
                    headers=self._get_headers(),
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        return data.get("ingredients", [])
                    return []
        except Exception as err:
            _LOGGER.error("Error fetching excluded ingredients: %s", err)
            return []

    async def generate_weekly_plan(self) -> None:
        """Generate new weekly plan via API (async background task).

        This operation takes 30-120 seconds and runs in the background.
        The API returns 202 Accepted immediately.
        """
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.api_url}/api/weekly-plan/generate",
                    headers=self._get_headers(),
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as response:
                    if response.status != 202:
                        error_text = await response.text()
                        _LOGGER.error("Failed to generate weekly plan: %s", error_text)
                        raise UpdateFailed(f"Failed to generate weekly plan: {error_text}")
                    _LOGGER.info("Weekly plan generation started (background task)")
        except aiohttp.ClientError as err:
            _LOGGER.error("Error generating weekly plan: %s", err)
            raise UpdateFailed(f"Error generating weekly plan: {err}") from err

    async def get_weekly_plan(self) -> dict[str, Any] | None:
        """Get the current weekly plan from API."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.api_url}/api/weekly-plan",
                    headers=self._get_headers(),
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as response:
                    if response.status == 200:
                        return await response.json()
                    elif response.status == 404:
                        return None
                    else:
                        error_text = await response.text()
                        _LOGGER.warning("Failed to get weekly plan: %s", error_text)
                        return None
        except Exception as err:
            _LOGGER.error("Error fetching weekly plan: %s", err)
            return None

    async def select_recipe(self, weekday: str, slot: str, recipe_index: int) -> None:
        """Select a recipe for a specific meal slot.

        Args:
            weekday: German weekday name (Montag, Dienstag, ...)
            slot: Meal slot (Mittagessen, Abendessen)
            recipe_index: Recipe index (0-4) or -1 for none
        """
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.api_url}/api/weekly-plan/select",
                    headers=self._get_headers(),
                    json={
                        "weekday": weekday,
                        "slot": slot,
                        "recipe_index": recipe_index,
                    },
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        _LOGGER.error("Failed to select recipe: %s", error_text)
                        raise UpdateFailed(f"Failed to select recipe: {error_text}")
            # Refresh coordinator data after selection so UI updates
            await self.async_request_refresh()
        except aiohttp.ClientError as err:
            _LOGGER.error("Error selecting recipe: %s", err)
            raise UpdateFailed(f"Error selecting recipe: {err}") from err

    async def set_recipe_url(self, weekday: str, slot: str, recipe_url: str) -> None:
        """Set a recipe URL for a specific meal slot.

        Args:
            weekday: German weekday name (Montag, Dienstag, ...)
            slot: Meal slot (Mittagessen, Abendessen)
            recipe_url: URL to scrape and select
        """
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.api_url}/api/weekly-plan/select-url",
                    headers=self._get_headers(),
                    json={
                        "weekday": weekday,
                        "slot": slot,
                        "recipe_url": recipe_url,
                    },
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        _LOGGER.error("Failed to set recipe URL: %s", error_text)
                        raise UpdateFailed(f"Failed to set recipe URL: {error_text}")
            await self.async_request_refresh()
        except aiohttp.ClientError as err:
            _LOGGER.error("Error setting recipe URL: %s", err)
            raise UpdateFailed(f"Error setting recipe URL: {err}") from err

    async def delete_weekly_plan(self) -> None:
        """Delete the current weekly plan via API."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.delete(
                    f"{self.api_url}/api/weekly-plan",
                    headers=self._get_headers(),
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as response:
                    if response.status != 204:
                        error_text = await response.text()
                        _LOGGER.error("Failed to delete weekly plan: %s", error_text)
                        raise UpdateFailed(f"Failed to delete weekly plan: {error_text}")
        except aiohttp.ClientError as err:
            _LOGGER.error("Error deleting weekly plan: %s", err)
            raise UpdateFailed(f"Error deleting weekly plan: {err}") from err

    async def get_config(self) -> dict[str, Any] | None:
        """Get configuration from API."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.api_url}/api/config",
                    headers=self._get_headers(),
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as response:
                    if response.status == 200:
                        return await response.json()
                    return None
        except Exception as err:
            _LOGGER.error("Error fetching config: %s", err)
            return None

    async def set_household_size(self, size: int) -> None:
        """Set household size via API.

        Args:
            size: Number of people (1-10)
        """
        try:
            async with aiohttp.ClientSession() as session:
                async with session.put(
                    f"{self.api_url}/api/config",
                    headers=self._get_headers(),
                    json={"household_size": size},
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        _LOGGER.error("Failed to set household size: %s", error_text)
                        raise UpdateFailed(f"Failed to set household size: {error_text}")
            # Refresh coordinator data after config update
            await self.async_request_refresh()
        except aiohttp.ClientError as err:
            _LOGGER.error("Error setting household size: %s", err)
            raise UpdateFailed(f"Error setting household size: {err}") from err

    async def set_multi_day(
        self,
        primary_weekday: str,
        primary_slot: str,
        reuse_slots: list[dict],
    ) -> None:
        """Configure multi-day meal prep via API.

        Args:
            primary_weekday: Weekday when cooking
            primary_slot: Meal slot (Mittagessen/Abendessen)
            reuse_slots: List of {"weekday": "...", "slot": "..."} dicts
        """
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.api_url}/api/weekly-plan/multi-day",
                    headers=self._get_headers(),
                    json={
                        "primary_weekday": primary_weekday,
                        "primary_slot": primary_slot,
                        "reuse_slots": reuse_slots,
                    },
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        _LOGGER.error("Failed to set multi-day: %s", error_text)
                        raise UpdateFailed(f"Failed to set multi-day: {error_text}")
            await self.async_request_refresh()
        except aiohttp.ClientError as err:
            _LOGGER.error("Error setting multi-day: %s", err)
            raise UpdateFailed(f"Error setting multi-day: {err}") from err

    async def clear_multi_day(self, weekday: str, slot: str) -> None:
        """Clear multi-day configuration via API.

        Args:
            weekday: Weekday
            slot: Meal slot
        """
        try:
            async with aiohttp.ClientSession() as session:
                async with session.delete(
                    f"{self.api_url}/api/weekly-plan/multi-day/{weekday}/{slot}",
                    headers=self._get_headers(),
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        _LOGGER.error("Failed to clear multi-day: %s", error_text)
                        raise UpdateFailed(f"Failed to clear multi-day: {error_text}")
            await self.async_request_refresh()
        except aiohttp.ClientError as err:
            _LOGGER.error("Error clearing multi-day: %s", err)
            raise UpdateFailed(f"Error clearing multi-day: {err}") from err

    async def get_multi_day_groups(self) -> list[dict]:
        """Get all multi-day groups.

        Returns:
            List of multi-day group dicts
        """
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.api_url}/api/weekly-plan/multi-day",
                    headers=self._get_headers(),
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as response:
                    if response.status == 200:
                        return await response.json()
            return []
        except Exception as err:
            _LOGGER.error("Error fetching multi-day groups: %s", err)
            return []

    async def get_multi_day_preferences(self) -> list[dict]:
        """Get stored multi-day preferences for future plan generation."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.api_url}/api/weekly-plan/multi-day/preferences",
                    headers=self._get_headers(),
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        return data.get("groups", [])
            return []
        except Exception as err:
            _LOGGER.error("Error fetching multi-day preferences: %s", err)
            return []

    async def set_multi_day_preferences(self, groups: list[dict]) -> None:
        """Set multi-day preferences for future plan generation."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.put(
                    f"{self.api_url}/api/weekly-plan/multi-day/preferences",
                    headers=self._get_headers(),
                    json={"groups": groups},
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        _LOGGER.error("Failed to set multi-day preferences: %s", error_text)
                        raise UpdateFailed(f"Failed to set multi-day preferences: {error_text}")
            await self.async_request_refresh()
        except aiohttp.ClientError as err:
            _LOGGER.error("Error setting multi-day preferences: %s", err)
            raise UpdateFailed(f"Error setting multi-day preferences: {err}") from err

    async def set_skipped_slots(self, slots: list[dict]) -> None:
        """Set skipped slots for plan generation."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.put(
                    f"{self.api_url}/api/weekly-plan/skip-slots",
                    headers=self._get_headers(),
                    json={"slots": slots},
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        _LOGGER.error("Failed to set skipped slots: %s", error_text)
                        raise UpdateFailed(f"Failed to set skipped slots: {error_text}")
            await self.async_request_refresh()
        except aiohttp.ClientError as err:
            _LOGGER.error("Error setting skipped slots: %s", err)
            raise UpdateFailed(f"Error setting skipped slots: {err}") from err

    async def fetch_recipes(self, delay_seconds: float = 0.5) -> None:
        """Trigger background recipe fetch from meal URLs."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.api_url}/api/recipes/fetch",
                    headers=self._get_headers(),
                    params={"delay_seconds": delay_seconds},
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        _LOGGER.error("Failed to start recipe fetch: %s", error_text)
                        raise UpdateFailed(f"Failed to start recipe fetch: {error_text}")
        except aiohttp.ClientError as err:
            _LOGGER.error("Error starting recipe fetch: %s", err)
            raise UpdateFailed(f"Error starting recipe fetch: {err}") from err

    async def get_shopping_list(self) -> dict[str, Any] | None:
        """Get aggregated shopping list from API.

        Returns:
            Shopping list dict or None
        """
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.api_url}/api/shopping-list",
                    headers=self._get_headers(),
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as response:
                    if response.status == 200:
                        return await response.json()
                    elif response.status == 404:
                        return None
                    else:
                        error_text = await response.text()
                        _LOGGER.warning("Failed to get shopping list: %s", error_text)
                        return None
        except Exception as err:
            _LOGGER.error("Error fetching shopping list: %s", err)
            return None

    async def get_split_shopping_list(self) -> dict[str, Any] | None:
        """Get shopping list split by store (Bioland/Rewe).

        Returns:
            Split shopping list dict or None
        """
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.api_url}/api/shopping-list/split",
                    headers=self._get_headers(),
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as response:
                    if response.status == 200:
                        return await response.json()
                    elif response.status == 404:
                        return None
                    else:
                        error_text = await response.text()
                        _LOGGER.warning("Failed to get split shopping list: %s", error_text)
                        return None
        except Exception as err:
            _LOGGER.error("Error fetching split shopping list: %s", err)
            return None
