"""Support for Aidot switches."""

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import (
    CONNECTION_NETWORK_MAC,
    DeviceInfo,
    format_mac,
)
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import AidotConfigEntry, AidotDeviceUpdateCoordinator


def _is_switch_device(coordinator, device_id: str) -> bool:
    """Check if device is a plug/switch (not a light)."""
    device_type = coordinator.device_types.get(device_id, "")
    # Accept devices that have 'plug' or 'switch' in their type
    # Explicitly exclude lights
    is_plug = "plug" in device_type.lower()
    is_switch = "switch" in device_type.lower()
    is_light = "light" in device_type.lower() or "bulb" in device_type.lower()
    
    return (is_plug or is_switch) and not is_light


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AidotConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Switch."""
    coordinator = entry.runtime_data
    lists_added: set[str] = set()

    @callback
    def add_entities() -> None:
        """Add switch entities."""
        nonlocal lists_added
        new_lists = {
            device_coordinator.device_client.device_id
            for device_coordinator in coordinator.device_coordinators.values()
            if _is_switch_device(coordinator, device_coordinator.device_client.device_id)
        }

        if new_lists - lists_added:
            async_add_entities(
                AidotSwitch(hass, coordinator.device_coordinators[device_id])
                for device_id in new_lists
            )
            lists_added |= new_lists
        elif lists_added - new_lists:
            removed_device_ids = lists_added - new_lists
            for device_id in removed_device_ids:
                entity_registry = er.async_get(hass)
                if entity := entity_registry.async_get_entity_id(
                    "switch", DOMAIN, device_id
                ):
                    entity_registry.async_remove(entity)
            lists_added = lists_added - removed_device_ids

    coordinator.async_add_listener(add_entities)
    add_entities()


class AidotSwitch(CoordinatorEntity[AidotDeviceUpdateCoordinator], SwitchEntity):
    """Representation of a Aidot Wi-Fi Switch."""

    _attr_has_entity_name = True
    _attr_name = None

    def __init__(
        self, hass: HomeAssistant, coordinator: AidotDeviceUpdateCoordinator
    ) -> None:
        """Initialize the switch."""
        super().__init__(coordinator)
        self._attr_unique_id = coordinator.device_client.info.dev_id

        model_id = coordinator.device_client.info.model_id
        manufacturer = model_id.split(".")[0]
        model = model_id[len(manufacturer) + 1 :]
        mac = format_mac(coordinator.device_client.info.mac)

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._attr_unique_id)},
            connections={(CONNECTION_NETWORK_MAC, mac)},
            manufacturer=manufacturer,
            model=model,
            name=coordinator.device_client.info.name,
            hw_version=coordinator.device_client.info.hw_version,
        )
        self._update_status()
        coordinator.device_client.set_status_fresh_cb(self._device_status_callback)

    def _device_status_callback(self, status) -> None:
        self._update_status()
        self.async_write_ha_state()

    def _update_status(self) -> None:
        import logging
        _LOGGER = logging.getLogger(__name__)
        _LOGGER.debug(f"Switch {self._attr_unique_id}: online={self.coordinator.data.online}, on={self.coordinator.data.on}")
        self._attr_available = self.coordinator.data.online
        self._attr_is_on = self.coordinator.data.on

    @callback
    def _handle_coordinator_update(self) -> None:
        """Update."""
        self._update_status()
        super()._handle_coordinator_update()

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on."""
        self.coordinator.data.on = True
        self._attr_is_on = True
        await self.coordinator.device_client.async_turn_on()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off."""
        self.coordinator.data.on = False
        self._attr_is_on = False
        await self.coordinator.device_client.async_turn_off()
