"""Config flow for KI-Essensplaner integration."""

from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_URL

from .const import CONF_API_TOKEN, CONF_API_URL, DEFAULT_API_URL, DOMAIN


class EssensplanerConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for KI-Essensplaner."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            api_url = user_input[CONF_API_URL]
            api_token = user_input.get(CONF_API_TOKEN)

            # Validate the API connection
            try:
                valid = await self._test_api_connection(api_url, api_token)
                if valid:
                    return self.async_create_entry(
                        title="KI-Essensplaner",
                        data={
                            CONF_API_URL: api_url,
                            CONF_API_TOKEN: api_token,
                        },
                    )
                else:
                    errors["base"] = "cannot_connect"
            except Exception:
                errors["base"] = "cannot_connect"

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_API_URL, default=DEFAULT_API_URL): str,
                    vol.Optional(CONF_API_TOKEN): str,
                }
            ),
            errors=errors,
        )

    async def _test_api_connection(
        self, api_url: str, api_token: str | None
    ) -> bool:
        """Test the API connection."""
        try:
            async with aiohttp.ClientSession() as session:
                headers = {}
                if api_token:
                    headers["Authorization"] = f"Bearer {api_token}"

                async with session.get(
                    f"{api_url.rstrip('/')}/api/health",
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as response:
                    return response.status == 200
        except Exception:
            return False
