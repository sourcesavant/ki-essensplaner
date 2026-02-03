"""Config flow for KI-Essensplaner integration."""

from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_URL
from homeassistant.helpers import selector

from .const import CONF_API_TOKEN, CONF_API_URL, DEFAULT_API_URL, DOMAIN


class EssensplanerConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for KI-Essensplaner."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._api_url: str | None = None
        self._api_token: str | None = None
        self._notebooks: list[dict[str, str]] = []
        self._device_code: str | None = None
        self._verification_uri: str | None = None

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
                    # Store for later steps
                    self._api_url = api_url
                    self._api_token = api_token

                    # Check if onboarding is needed
                    onboarding_status = await self._get_onboarding_status(api_url, api_token)
                    if onboarding_status and not onboarding_status.get("ready_for_use", False):
                        # Continue to onboarding
                        return await self.async_step_onboarding_check()
                    else:
                        # Skip onboarding, create entry directly
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

    async def _get_onboarding_status(
        self, api_url: str, api_token: str | None
    ) -> dict[str, Any] | None:
        """Get onboarding status from API."""
        try:
            async with aiohttp.ClientSession() as session:
                headers = {}
                if api_token:
                    headers["Authorization"] = f"Bearer {api_token}"

                async with session.get(
                    f"{api_url.rstrip('/')}/api/onboarding/status",
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as response:
                    if response.status == 200:
                        return await response.json()
        except Exception:
            pass
        return None

    async def _get_notebooks(
        self, api_url: str, api_token: str | None
    ) -> list[dict[str, str]]:
        """Get available notebooks from API."""
        try:
            async with aiohttp.ClientSession() as session:
                headers = {}
                if api_token:
                    headers["Authorization"] = f"Bearer {api_token}"

                async with session.get(
                    f"{api_url.rstrip('/')}/api/onboarding/onenote/notebooks",
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        return data.get("notebooks", [])
        except Exception:
            pass
        return []

    async def _trigger_import(
        self, api_url: str, api_token: str | None, notebook_ids: list[str]
    ) -> bool:
        """Trigger data import from notebooks."""
        try:
            async with aiohttp.ClientSession() as session:
                headers = {"Content-Type": "application/json"}
                if api_token:
                    headers["Authorization"] = f"Bearer {api_token}"

                async with session.post(
                    f"{api_url.rstrip('/')}/api/onboarding/import",
                    headers=headers,
                    json={"notebook_ids": notebook_ids},
                    timeout=aiohttp.ClientTimeout(total=120),
                ) as response:
                    return response.status == 200
        except Exception:
            return False

    async def _trigger_profile_generation(
        self, api_url: str, api_token: str | None
    ) -> bool:
        """Trigger profile generation."""
        try:
            async with aiohttp.ClientSession() as session:
                headers = {}
                if api_token:
                    headers["Authorization"] = f"Bearer {api_token}"

                async with session.post(
                    f"{api_url.rstrip('/')}/api/onboarding/profile/generate",
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=60),
                ) as response:
                    return response.status == 200
        except Exception:
            return False

    async def async_step_onboarding_check(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Check onboarding status and guide user."""
        status = await self._get_onboarding_status(self._api_url, self._api_token)

        if not status:
            # Can't get status, skip onboarding
            return self.async_create_entry(
                title="KI-Essensplaner",
                data={
                    CONF_API_URL: self._api_url,
                    CONF_API_TOKEN: self._api_token,
                },
            )

        if user_input is not None:
            if user_input.get("skip_onboarding"):
                # User chose to skip
                return self.async_create_entry(
                    title="KI-Essensplaner",
                    data={
                        CONF_API_URL: self._api_url,
                        CONF_API_TOKEN: self._api_token,
                    },
                )
            else:
                # Continue with onboarding
                if not status.get("onenote_authenticated"):
                    return await self.async_step_onenote_auth()
                elif not status.get("data_imported"):
                    return await self.async_step_notebook_selection()
                elif not status.get("profile_generated"):
                    return await self.async_step_profile_generation()

        # Show onboarding check form - determine next step text ourselves
        if not status.get("azure_configured"):
            next_step = "Azure in der Add-on Konfiguration einrichten"
        elif not status.get("onenote_authenticated"):
            next_step = "Klicken Sie auf 'Absenden' um OneNote zu verbinden"
        elif not status.get("data_imported"):
            next_step = "Daten werden importiert..."
        elif not status.get("profile_generated"):
            next_step = "Profil wird generiert..."
        else:
            next_step = "Bereit!"

        return self.async_show_form(
            step_id="onboarding_check",
            data_schema=vol.Schema(
                {
                    vol.Required("skip_onboarding", default=False): bool,
                }
            ),
            description_placeholders={
                "next_step": next_step,
                "azure_configured": "✓" if status.get("azure_configured") else "✗",
                "onenote_auth": "✓" if status.get("onenote_authenticated") else "✗",
                "data_imported": "✓" if status.get("data_imported") else "✗",
                "profile_generated": "✓" if status.get("profile_generated") else "✗",
            },
        )

    async def _start_device_flow(self) -> dict[str, Any] | None:
        """Start the OneNote device code flow."""
        try:
            async with aiohttp.ClientSession() as session:
                headers = {"Content-Type": "application/json"}
                if self._api_token:
                    headers["Authorization"] = f"Bearer {self._api_token}"

                async with session.post(
                    f"{self._api_url.rstrip('/')}/api/onboarding/onenote/auth/start",
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as response:
                    if response.status == 200:
                        return await response.json()
                    elif response.status == 400:
                        # Already authenticated
                        return {"already_authenticated": True}
        except Exception:
            pass
        return None

    async def _complete_device_flow(self) -> dict[str, Any] | None:
        """Complete the OneNote device code flow (waits for user to authenticate)."""
        try:
            async with aiohttp.ClientSession() as session:
                headers = {"Content-Type": "application/json"}
                if self._api_token:
                    headers["Authorization"] = f"Bearer {self._api_token}"

                async with session.post(
                    f"{self._api_url.rstrip('/')}/api/onboarding/onenote/auth/complete",
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=320),  # 5+ minutes
                ) as response:
                    if response.status == 200:
                        return await response.json()
        except Exception:
            pass
        return None

    async def async_step_onenote_auth(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Start OneNote authentication and show device code."""
        # If user submitted the form, proceed to wait for auth completion
        if user_input is not None:
            return await self.async_step_onenote_auth_wait()

        # Start the device flow to get the code
        flow_data = await self._start_device_flow()

        if flow_data and flow_data.get("already_authenticated"):
            # Already authenticated, skip to next step
            return await self.async_step_onenote_auth_wait({"skip": True})

        if not flow_data or "user_code" not in flow_data:
            return self.async_abort(reason="auth_start_failed")

        # Store the code for display
        self._device_code = flow_data["user_code"]
        self._verification_uri = flow_data["verification_uri"]

        # Show the code to the user
        return self.async_show_form(
            step_id="onenote_auth",
            data_schema=vol.Schema({}),
            description_placeholders={
                "user_code": self._device_code,
                "verification_uri": self._verification_uri,
            },
        )

    async def async_step_onenote_auth_wait(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Wait for OneNote authentication to complete."""
        if user_input and user_input.get("skip"):
            # Already authenticated, proceed to notebook selection
            return await self.async_step_notebook_selection()

        # Wait for the authentication to complete
        result = await self._complete_device_flow()

        if result and result.get("authenticated"):
            # Success! Now let user select notebooks
            return await self.async_step_notebook_selection()
        else:
            return self.async_abort(reason="auth_failed")

    async def async_step_notebook_selection(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Select notebooks to import."""
        if user_input is not None:
            selected = user_input.get("notebooks", [])
            if selected:
                # Trigger import
                success = await self._trigger_import(
                    self._api_url, self._api_token, selected
                )
                if success:
                    return await self.async_step_profile_generation()
                else:
                    return self.async_abort(reason="import_failed")
            else:
                # No notebooks selected, skip import
                return await self.async_step_profile_generation()

        # Fetch notebooks
        notebooks = await self._get_notebooks(self._api_url, self._api_token)
        self._notebooks = notebooks

        if not notebooks:
            # No notebooks available - abort with clear error
            return self.async_abort(reason="no_notebooks")

        # Create multi-select options
        notebook_options = {nb["id"]: nb["name"] for nb in notebooks}

        return self.async_show_form(
            step_id="notebook_selection",
            data_schema=vol.Schema(
                {
                    vol.Optional("notebooks"): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[
                                {"label": name, "value": id}
                                for id, name in notebook_options.items()
                            ],
                            multiple=True,
                            mode=selector.SelectSelectorMode.LIST,
                        )
                    ),
                }
            ),
        )

    async def async_step_profile_generation(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Generate preference profile."""
        if user_input is not None:
            # Trigger profile generation
            success = await self._trigger_profile_generation(
                self._api_url, self._api_token
            )

            # Create entry regardless of profile generation success
            # (profile can be generated later)
            return self.async_create_entry(
                title="KI-Essensplaner",
                data={
                    CONF_API_URL: self._api_url,
                    CONF_API_TOKEN: self._api_token,
                },
            )

        return self.async_show_form(
            step_id="profile_generation",
            data_schema=vol.Schema({}),
        )
