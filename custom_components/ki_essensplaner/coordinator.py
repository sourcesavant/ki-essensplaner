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

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from API with offline caching support."""
        try:
            async with aiohttp.ClientSession() as session:
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
                    else:
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

        except aiohttp.ClientError as err:
            _LOGGER.error("Error connecting to API: %s", err)
            # Return cached data if available, otherwise raise
            if self._last_valid_data is not None:
                cached = self._last_valid_data.copy()
                cached["cached"] = True
                _LOGGER.info("Using cached data due to connection error")
                return cached
            raise UpdateFailed(f"Error connecting to API: {err}") from err
        except Exception as err:
            _LOGGER.error("Unexpected error: %s", err)
            # Return cached data if available, otherwise raise
            if self._last_valid_data is not None:
                cached = self._last_valid_data.copy()
                cached["cached"] = True
                _LOGGER.info("Using cached data due to unexpected error")
                return cached
            raise UpdateFailed(f"Unexpected error: {err}") from err
