"""One switch per Firewalla rule: on = active, off = paused.

Rule switches are created disabled; enable the ones you want in the UI.
The MSP API pauses a rule until it is resumed (no duration in the official docs),
so use an automation or script if you want a timed pause.
"""
from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import FirewallaConfigEntry
from .api import FirewallaApiError
from .coordinator import FirewallaCoordinator
from .entity import FirewallaBoxEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: FirewallaConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    known: set[str] = set()

    @callback
    def _add_new_rules() -> None:
        new = [
            FirewallaRuleSwitch(coordinator, rule["gid"], rule_id)
            for rule_id, rule in coordinator.data.rules.items()
            if rule_id not in known and rule.get("gid") in coordinator.data.boxes
        ]
        known.update(e.rule_id for e in new)
        if new:
            async_add_entities(new)

    _add_new_rules()
    entry.async_on_unload(coordinator.async_add_listener(_add_new_rules))


def _rule_label(rule: dict[str, Any]) -> str:
    notes = (rule.get("notes") or "").strip()
    if notes:
        return notes
    action = (rule.get("action") or "rule").capitalize()
    target = rule.get("target") or {}
    scope = rule.get("scope") or {}
    label = f"{action} {target.get('value') or target.get('type') or ''}".strip()
    if scope.get("value"):
        label += f" for {scope['value']}"
    return label


class FirewallaRuleSwitch(FirewallaBoxEntity, SwitchEntity):
    _attr_entity_registry_enabled_default = False
    _attr_icon = "mdi:shield-lock"

    def __init__(self, coordinator: FirewallaCoordinator, gid: str, rule_id: str) -> None:
        super().__init__(coordinator, gid, f"rule_{rule_id}")
        self.rule_id = rule_id
        self._attr_name = f"Rule: {_rule_label(coordinator.data.rules[rule_id])}"

    @property
    def _rule(self) -> dict[str, Any]:
        return self.coordinator.data.rules.get(self.rule_id, {})

    @property
    def available(self) -> bool:
        return super().available and self.rule_id in self.coordinator.data.rules

    @property
    def is_on(self) -> bool:
        return self._rule.get("status") == "active"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        r = self._rule
        return {
            "rule_id": self.rule_id,
            "action": r.get("action"),
            "status": r.get("status"),
            "target": r.get("target"),
            "scope": r.get("scope"),
            "direction": r.get("direction"),
            "resume_ts": r.get("resumeTs"),
        }

    async def _set(self, active: bool) -> None:
        try:
            if active:
                await self.coordinator.client.resume_rule(self.rule_id)
            else:
                await self.coordinator.client.pause_rule(self.rule_id)
        except FirewallaApiError as err:
            raise HomeAssistantError(f"Firewalla rule update failed: {err}") from err
        # Optimistic update, then confirm on next poll.
        self._rule["status"] = "active" if active else "paused"
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._set(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._set(False)
