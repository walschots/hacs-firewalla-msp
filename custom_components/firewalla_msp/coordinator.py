"""Polling coordinator for Firewalla MSP."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import FirewallaApiError, FirewallaAuthError, FirewallaMspClient
from .const import (
    ALARM_FETCH_LIMIT,
    ALARM_STATUS_ACTIVE,
    ALARM_TYPES,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    EVENT_ALARM,
    WAN_STATUS,
)

_LOGGER = logging.getLogger(__name__)


def _to_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


@dataclass
class FirewallaData:
    """Snapshot of everything the entities read."""

    boxes: dict[str, dict[str, Any]] = field(default_factory=dict)
    devices: dict[str, dict[str, Any]] = field(default_factory=dict)
    rules: dict[str, dict[str, Any]] = field(default_factory=dict)
    alarms: list[dict[str, Any]] = field(default_factory=list)
    rules_supported: bool = True

    def active_alarms(self, gid: str) -> list[dict[str, Any]]:
        return [
            a
            for a in self.alarms
            if a.get("gid") == gid and _to_int(a.get("status"), ALARM_STATUS_ACTIVE) == ALARM_STATUS_ACTIVE
        ]

    def latest_alarm(self, gid: str) -> dict[str, Any] | None:
        box_alarms = [a for a in self.alarms if a.get("gid") == gid]
        if not box_alarms:
            return None
        return max(box_alarms, key=lambda a: float(a.get("ts") or 0))

    def box_devices(self, gid: str) -> list[dict[str, Any]]:
        return [d for d in self.devices.values() if d.get("gid") == gid]


class FirewallaCoordinator(DataUpdateCoordinator[FirewallaData]):
    """Fetch boxes, devices, rules and alarms; fire an event per new alarm."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, client: FirewallaMspClient) -> None:
        interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(seconds=interval),
        )
        self.client = client
        self._seen_alarms: set[tuple[str, str]] | None = None
        self._rules_supported = True

    async def _async_update_data(self) -> FirewallaData:
        try:
            boxes = await self.client.get_boxes()
            devices = await self.client.get_devices()
            alarms = await self.client.get_alarms(ALARM_FETCH_LIMIT)
            rules: list[dict[str, Any]] = []
            if self._rules_supported:
                try:
                    rules = await self.client.get_rules()
                except FirewallaAuthError:
                    raise
                except FirewallaApiError as err:
                    # GET /v2/rules needs MSP 2.7.0+; keep the rest working without it.
                    _LOGGER.warning("Rules unavailable, rule switches disabled: %s", err)
                    self._rules_supported = False
        except FirewallaAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except FirewallaApiError as err:
            raise UpdateFailed(str(err)) from err

        data = FirewallaData(
            boxes={b["gid"]: b for b in boxes if b.get("gid")},
            devices={d["id"]: d for d in devices if d.get("id")},
            rules={str(r["id"]): r for r in rules if r.get("id") is not None},
            alarms=alarms,
            rules_supported=self._rules_supported,
        )
        self._fire_new_alarm_events(data)
        return data

    def _fire_new_alarm_events(self, data: FirewallaData) -> None:
        keys = {(str(a.get("gid")), str(a.get("aid"))) for a in data.alarms}
        if self._seen_alarms is None:
            # First poll after start-up: remember what exists, don't replay history.
            self._seen_alarms = keys
            return

        new = [
            a
            for a in data.alarms
            if (str(a.get("gid")), str(a.get("aid"))) not in self._seen_alarms
        ]
        # Bound memory: only keep keys still in the latest window plus the new ones.
        self._seen_alarms = keys

        for alarm in sorted(new, key=lambda a: float(a.get("ts") or 0)):
            self.hass.bus.async_fire(EVENT_ALARM, self.alarm_event_data(alarm, data))

    @staticmethod
    def alarm_event_data(alarm: dict[str, Any], data: FirewallaData) -> dict[str, Any]:
        atype = _to_int(alarm.get("type"))
        box = data.boxes.get(alarm.get("gid", ""), {})
        device = alarm.get("device") or {}
        remote = alarm.get("remote") or {}
        wan = alarm.get("wan") or {}
        event: dict[str, Any] = {
            "aid": alarm.get("aid"),
            "type": atype,
            "type_name": ALARM_TYPES.get(atype, f"Type {atype}"),
            "message": alarm.get("message"),
            "ts": alarm.get("ts"),
            "box_gid": alarm.get("gid"),
            "box_name": box.get("name"),
            "device_id": device.get("id"),
            "device_name": device.get("name"),
            "device_ip": device.get("ip"),
            "remote_ip": remote.get("ip"),
            "remote_domain": remote.get("domain"),
            "remote_category": remote.get("category"),
            "direction": alarm.get("direction"),
        }
        if wan:
            event.update(
                {
                    "wan_name": wan.get("name"),
                    "wan_status": WAN_STATUS.get(_to_int(wan.get("status")), wan.get("status")),
                    "wan_active": wan.get("active"),
                    "wan_switched": wan.get("switched"),
                }
            )
        return event
