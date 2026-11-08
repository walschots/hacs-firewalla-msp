"""Sensors per Firewalla box."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import FirewallaConfigEntry
from .coordinator import FirewallaCoordinator, FirewallaData
from .entity import FirewallaBoxEntity


@dataclass(frozen=True, kw_only=True)
class FirewallaSensorDescription(SensorEntityDescription):
    value_fn: Callable[[FirewallaData, str], Any]


SENSORS: tuple[FirewallaSensorDescription, ...] = (
    FirewallaSensorDescription(
        key="active_alarms",
        translation_key="active_alarms",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data, gid: len(data.active_alarms(gid)),
    ),
    FirewallaSensorDescription(
        key="devices_online",
        translation_key="devices_online",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data, gid: sum(1 for d in data.box_devices(gid) if d.get("online")),
    ),
    FirewallaSensorDescription(
        key="devices_offline",
        translation_key="devices_offline",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data, gid: sum(1 for d in data.box_devices(gid) if not d.get("online")),
    ),
    FirewallaSensorDescription(
        key="public_ip",
        translation_key="public_ip",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data, gid: data.boxes.get(gid, {}).get("publicIP"),
    ),
    FirewallaSensorDescription(
        key="firmware",
        translation_key="firmware",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data, gid: data.boxes.get(gid, {}).get("version"),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: FirewallaConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    entities: list[SensorEntity] = []
    for gid in coordinator.data.boxes:
        entities.extend(FirewallaBoxSensor(coordinator, gid, desc) for desc in SENSORS)
        entities.append(FirewallaLatestAlarm(coordinator, gid))
    async_add_entities(entities)


class FirewallaBoxSensor(FirewallaBoxEntity, SensorEntity):
    entity_description: FirewallaSensorDescription

    def __init__(
        self, coordinator: FirewallaCoordinator, gid: str, description: FirewallaSensorDescription
    ) -> None:
        super().__init__(coordinator, gid, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> Any:
        return self.entity_description.value_fn(self.coordinator.data, self.gid)


class FirewallaLatestAlarm(FirewallaBoxEntity, SensorEntity):
    """Time of the newest alarm, with its details as attributes."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_translation_key = "latest_alarm"

    def __init__(self, coordinator: FirewallaCoordinator, gid: str) -> None:
        super().__init__(coordinator, gid, "latest_alarm")

    @property
    def _alarm(self) -> dict[str, Any] | None:
        return self.coordinator.data.latest_alarm(self.gid)

    @property
    def native_value(self) -> datetime | None:
        alarm = self._alarm
        if not alarm or not alarm.get("ts"):
            return None
        return datetime.fromtimestamp(float(alarm["ts"]), tz=UTC)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        alarm = self._alarm
        if not alarm:
            return {}
        return FirewallaCoordinator.alarm_event_data(alarm, self.coordinator.data)
