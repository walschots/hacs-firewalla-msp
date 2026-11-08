"""Binary sensors: box online, and online state of devices you choose to track."""
from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import FirewallaConfigEntry
from .const import CONF_TRACKED_DEVICES
from .coordinator import FirewallaCoordinator
from .entity import FirewallaBoxEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: FirewallaConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    entities: list[BinarySensorEntity] = [
        FirewallaBoxOnline(coordinator, gid) for gid in coordinator.data.boxes
    ]
    for device_id in entry.options.get(CONF_TRACKED_DEVICES, []):
        device = coordinator.data.devices.get(device_id)
        if device and device.get("gid") in coordinator.data.boxes:
            entities.append(FirewallaTrackedDevice(coordinator, device["gid"], device_id))
    async_add_entities(entities)


class FirewallaBoxOnline(FirewallaBoxEntity, BinarySensorEntity):
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_translation_key = "box_online"

    def __init__(self, coordinator: FirewallaCoordinator, gid: str) -> None:
        super().__init__(coordinator, gid, "online")

    @property
    def is_on(self) -> bool | None:
        return self.box.get("online")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "public_ip": self.box.get("publicIP"),
            "mode": self.box.get("mode"),
            "last_seen": self.box.get("lastSeen"),
        }


class FirewallaTrackedDevice(FirewallaBoxEntity, BinarySensorEntity):
    """Online/offline for one network device (e.g. Powerwall gateway, Homebridge)."""

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def __init__(self, coordinator: FirewallaCoordinator, gid: str, device_id: str) -> None:
        super().__init__(coordinator, gid, f"device_{device_id}")
        self.device_id = device_id
        name = coordinator.data.devices.get(device_id, {}).get("name") or device_id
        self._attr_name = name

    @property
    def _device(self) -> dict[str, Any]:
        return self.coordinator.data.devices.get(self.device_id, {})

    @property
    def available(self) -> bool:
        return super().available and self.device_id in self.coordinator.data.devices

    @property
    def is_on(self) -> bool | None:
        return self._device.get("online")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        d = self._device
        return {
            "ip": d.get("ip"),
            "mac": d.get("mac") or self.device_id,
            "vendor": d.get("macVendor"),
            "network": (d.get("network") or {}).get("name"),
            "group": (d.get("group") or {}).get("name"),
            "last_seen": d.get("lastSeen"),
        }
