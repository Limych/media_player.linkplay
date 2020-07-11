"""Config flow for LinkPlay."""
import media_player
from homeassistant import config_entries
from homeassistant.helpers import config_entry_flow

from . import DOMAIN

async def _async_has_devices(hass):
    """Return if there are devices that can be discovered."""
    return await hass.async_add_executor_job(upnp_discover)


config_entry_flow.register_discovery_flow(
    DOMAIN, "LinkPlay", _async_has_devices, config_entries.CONN_CLASS_LOCAL_PUSH
)
