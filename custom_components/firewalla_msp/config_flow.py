"""Config and options flow for Firewalla MSP."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import FirewallaApiError, FirewallaAuthError, FirewallaMspClient, normalize_domain
from .const import (
    CONF_MSP_DOMAIN,
    CONF_SCAN_INTERVAL,
    CONF_TOKEN,
    CONF_TRACKED_DEVICES,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MIN_SCAN_INTERVAL,
)

PASSWORD = TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))


async def _validate(hass, msp_domain: str, token: str) -> int:
    client = FirewallaMspClient(async_get_clientsession(hass), msp_domain, token)
    return len(await client.get_boxes())


class FirewallaMspConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            host = normalize_domain(user_input[CONF_MSP_DOMAIN])
            await self.async_set_unique_id(host)
            self._abort_if_unique_id_configured()
            try:
                count = await _validate(self.hass, host, user_input[CONF_TOKEN])
            except FirewallaAuthError:
                errors["base"] = "invalid_auth"
            except FirewallaApiError:
                errors["base"] = "cannot_connect"
            else:
                if count == 0:
                    errors["base"] = "no_boxes"
                else:
                    return self.async_create_entry(
                        title=host,
                        data={CONF_MSP_DOMAIN: host, CONF_TOKEN: user_input[CONF_TOKEN].strip()},
                    )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_MSP_DOMAIN): str,
                    vol.Required(CONF_TOKEN): PASSWORD,
                }
            ),
            errors=errors,
        )

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        entry = self._get_reauth_entry()
        if user_input is not None:
            try:
                await _validate(self.hass, entry.data[CONF_MSP_DOMAIN], user_input[CONF_TOKEN])
            except FirewallaAuthError:
                errors["base"] = "invalid_auth"
            except FirewallaApiError:
                errors["base"] = "cannot_connect"
            else:
                return self.async_update_reload_and_abort(
                    entry, data_updates={CONF_TOKEN: user_input[CONF_TOKEN].strip()}
                )
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_TOKEN): PASSWORD}),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return FirewallaMspOptionsFlow()


class FirewallaMspOptionsFlow(OptionsFlow):
    """Poll interval and which network devices get an online/offline sensor."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            user_input[CONF_SCAN_INTERVAL] = int(user_input[CONF_SCAN_INTERVAL])
            return self.async_create_entry(data=user_input)

        options = self.config_entry.options
        coordinator = getattr(self.config_entry, "runtime_data", None)
        devices = coordinator.data.devices if coordinator and coordinator.data else {}
        choices = sorted(
            (
                SelectOptionDict(
                    value=dev_id,
                    label=f"{d.get('name') or dev_id} ({d.get('ip') or 'no IP'})",
                )
                for dev_id, d in devices.items()
            ),
            key=lambda o: o["label"].lower(),
        )
        # Keep previously tracked devices selectable even if they're missing right now.
        for dev_id in options.get(CONF_TRACKED_DEVICES, []):
            if dev_id not in devices:
                choices.append(SelectOptionDict(value=dev_id, label=dev_id))

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_SCAN_INTERVAL,
                    default=options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=MIN_SCAN_INTERVAL, max=3600, step=10,
                        unit_of_measurement="s", mode=NumberSelectorMode.BOX,
                    )
                ),
                vol.Optional(
                    CONF_TRACKED_DEVICES,
                    default=options.get(CONF_TRACKED_DEVICES, []),
                ): SelectSelector(SelectSelectorConfig(options=choices, multiple=True)),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
