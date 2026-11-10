"""Polling coordinator for Firewalla MSP."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
import logging
import time
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    FirewallaApiError,
    FirewallaAuthError,
    FirewallaMspClient,
    FirewallaRateLimitError,
)
from .const import (
    ALARM_FETCH_LIMIT,
    ALARM_STATUS_ACTIVE,
    ALARM_TYPES,
    BACKOFF_INITIAL,
    BACKOFF_MAX,
    BOXES_INTERVAL,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    EVENT_ALARM,
    MIN_SCAN_INTERVAL,
    RULES_INTERVAL,
    WAN_STATUS,
)

_LOGGER = logging.getLogger(__name__)

# Back-off state per config entry, kept outside the coordinator so it survives
# setup retries (HA builds a new coordinator on every ConfigEntryNotReady retry,
# roughly every 80 s, which would otherwise ignore the back-off and keep the
# MSP rate limit tripped). Values: (backoff_until monotonic, last delay in s).
_BACKOFF: dict[str, tuple[float, float]] = {}


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
        interval = max(
            int(entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)), MIN_SCAN_INTERVAL
        )
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
        # Monotonic timestamps of the last successful slow-cadence fetches.
        self._boxes_fetched: float | None = None
        self._rules_fetched: float | None = None
        # Rate-limit back-off state (restored across setup retries).
        self._entry_id = entry.entry_id
        self._backoff_until, self._backoff = _BACKOFF.get(self._entry_id, (0.0, 0.0))

    def request_rules_refresh(self) -> None:
        """Fetch rules on the next poll (after a rule was paused/resumed)."""
        self._rules_fetched = None

    def _start_backoff(self, err: FirewallaRateLimitError) -> float:
        if err.retry_after:
            delay = min(err.retry_after, BACKOFF_MAX)
        else:
            delay = min(self._backoff * 2 if self._backoff else BACKOFF_INITIAL, BACKOFF_MAX)
        self._backoff = delay
        self._backoff_until = time.monotonic() + delay
        _BACKOFF[self._entry_id] = (self._backoff_until, self._backoff)
        return delay

    async def _async_update_data(self) -> FirewallaData:
        now = time.monotonic()
        prev = self.data

        if now < self._backoff_until:
            if prev is not None:
                # Still backing off: keep entities on their last known values.
                return prev
            wait = int(self._backoff_until - now)
            raise UpdateFailed(f"Rate limited by Firewalla MSP; next try in {wait} s")

        boxes = prev.boxes if prev else {}
        devices = prev.devices if prev else {}
        alarms = prev.alarms if prev else []
        rules = prev.rules if prev else {}

        try:
            if (
                not boxes
                or self._boxes_fetched is None
                or now - self._boxes_fetched >= BOXES_INTERVAL
            ):
                boxes = {b["gid"]: b for b in await self.client.get_boxes() if b.get("gid")}
                self._boxes_fetched = now

            devices = {d["id"]: d for d in await self.client.get_devices() if d.get("id")}
            alarms = await self.client.get_alarms(ALARM_FETCH_LIMIT)

            if self._rules_supported and (
                self._rules_fetched is None or now - self._rules_fetched >= RULES_INTERVAL
            ):
                try:
                    rules = {
                        str(r["id"]): r
                        for r in await self.client.get_rules()
                        if r.get("id") is not None
                    }
                    self._rules_fetched = now
                except (FirewallaAuthError, FirewallaRateLimitError):
                    raise
                except FirewallaApiError as err:
                    if err.status in (400, 404, 405, 501):
                        # GET /v2/rules needs MSP 2.7.0+; keep the rest working without it.
                        _LOGGER.warning("Rules unavailable, rule switches disabled: %s", err)
                        self._rules_supported = False
                        rules = {}
                    else:
                        # Transient failure: keep the last rules and try again next time.
                        _LOGGER.debug("Rules fetch failed, keeping last rules: %s", err)
        except FirewallaAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except FirewallaRateLimitError as err:
            delay = self._start_backoff(err)
            if prev is not None:
                _LOGGER.warning(
                    "Firewalla MSP rate limit hit; pausing polls for %d s and keeping last data",
                    delay,
                )
                return prev
            raise UpdateFailed(f"{err}; retrying in {int(delay)} s") from err
        except FirewallaApiError as err:
            raise UpdateFailed(str(err)) from err

        # A clean poll resets the back-off.
        self._backoff = 0.0
        self._backoff_until = 0.0
        _BACKOFF.pop(self._entry_id, None)

        data = FirewallaData(
            boxes=boxes,
            devices=devices,
            rules=rules if self._rules_supported else {},
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
