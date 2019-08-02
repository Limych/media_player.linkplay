"""Adds config flow for LinkPlay."""

from collections import OrderedDict

import voluptuous as vol
from homeassistant import config_entries

from . import DOMAIN


@config_entries.HANDLERS.register(DOMAIN)
class LinkPlayFlowHandler(config_entries.ConfigFlow):
    """Config flow for LinkPlay."""

    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_CLOUD_POLL

    def __init__(self):
        """Initialize."""
        self._errors = {}

    async def async_step_import(self,
                                user_input):  # pylint: disable=unused-argument
        """Import a config entry.
        Special type of import, we're not actually going to store any data.
        Instead, we're going to rely on the values that are in config file.
        """
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")

        return self.async_create_entry(title="configuration.yaml", data={})

    async def async_step_user(
            self, user_input={}
    ):  # pylint: disable=dangerous-default-value
        """Handle a flow initialized by the user."""
        self._errors = {}

        return self.async_abort(reason="in_development")

        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")
        if self.hass.data.get(DOMAIN):
            return self.async_abort(reason="single_instance_allowed")

        if user_input is not None:
            valid = await self._test_credentials(
                user_input["username"], user_input["password"]
            )
            if valid:
                return self.async_create_entry(title="", data=user_input)

            self._errors["base"] = "auth"
            return await self._show_config_form(user_input)

        return await self._show_config_form(user_input)

    async def _show_config_form(self, user_input):
        """Show the configuration form to edit location data."""

        # Defaults
        username = ""
        password = ""
        stream = 0

        if user_input is not None:
            if "username" in user_input:
                username = user_input["username"]
            if "password" in user_input:
                password = user_input["password"]
            if "stream" in user_input:
                stream = user_input["stream"]

        data_schema = OrderedDict()
        data_schema[vol.Required("username", default=username)] = str
        data_schema[vol.Required("password", default=password)] = str
        data_schema[vol.Required("stream", default=stream)] = int
        return self.async_show_form(
            step_id="user", data_schema=vol.Schema(data_schema),
            errors=self._errors
        )

    async def _test_credentials(self, username, password):
        """Return true if credentials is valid."""
        try:
            # client = Client(username, password)
            return True
        except Exception:  # pylint: disable=broad-except
            pass
        return False

    async def async_step_ssdp(self, info):  # pylint: disable=unused-argument
        """Handle a flow initialized by SSDP/UPNP."""
        self._errors = {}

        return self.async_abort(reason="in_development")
