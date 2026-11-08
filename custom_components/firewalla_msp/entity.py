"""Shared entity base."""
from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import FirewallaCoordinator


class FirewallaBoxEntity(CoordinatorEntity[FirewallaCoordinator]):
    """An entity that belongs to one Firewalla box (HA device)."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: FirewallaCoordinator, gid: str, key: str) -> None:
        super().__init__(coordinator)
        self.gid = gid
        self._attr_unique_id = f"{gid}_{key}"
        box = coordinator.data.boxes.get(gid, {})
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, gid)},
            name=box.get("name") or "Firewalla",
            manufacturer="Firewalla",
            model=(box.get("model") or "").title() or None,
            sw_version=box.get("version"),
            configuration_url=f"https://{coordinator.client.host}",
        )

    @property
    def box(self) -> dict:
        return self.coordinator.data.boxes.get(self.gid, {})

    @property
    def available(self) -> bool:
        return super().available and self.gid in self.coordinator.data.boxes
