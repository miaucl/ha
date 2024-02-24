"""Support for transport.opendata.ch."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
import logging
from typing import TYPE_CHECKING, Any

import voluptuous as vol

from homeassistant import config_entries, core
from homeassistant.components.sensor import (
    PLATFORM_SCHEMA,
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.config_entries import SOURCE_IMPORT
from homeassistant.const import CONF_NAME, UnitOfTime
from homeassistant.core import DOMAIN as HOMEASSISTANT_DOMAIN, HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.issue_registry import IssueSeverity, async_create_issue
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONF_DESTINATION,
    CONF_START,
    DEFAULT_NAME,
    DOMAIN,
    PLACEHOLDERS,
    SENSOR_CONNECTIONS_COUNT,
)
from .coordinator import DataConnection, SwissPublicTransportDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(seconds=90)

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_DESTINATION): cv.string,
        vol.Required(CONF_START): cv.string,
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
    }
)


@dataclass(kw_only=True, frozen=True)
class SwissPublicTransportSensorEntityDescription(SensorEntityDescription):
    """Describes swiss public transport sensor entity."""

    exists_fn: Callable[[DataConnection], bool] = lambda _: True
    value_fn: Callable[[DataConnection], Any]

    index: int | None = None


SENSORS: tuple[SwissPublicTransportSensorEntityDescription, ...] = (
    *[
        SwissPublicTransportSensorEntityDescription(
            key=f"departure{i or ''}",
            translation_key=f"departure{i}",
            device_class=SensorDeviceClass.TIMESTAMP,
            icon="mdi:bus-clock",
            value_fn=lambda data_connection: data_connection["departure"],
            exists_fn=lambda data_connection: data_connection is not None,
            index=i,
        )
        for i in range(SENSOR_CONNECTIONS_COUNT)
    ],
    SwissPublicTransportSensorEntityDescription(
        key="duration",
        translation_key="duration",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        icon="mdi:timeline-clock",
        value_fn=lambda data_connection: data_connection["duration"],
        exists_fn=lambda data_connection: data_connection is not None,
    ),
    SwissPublicTransportSensorEntityDescription(
        key="transfers",
        translation_key="transfers",
        icon="mdi:transit-transfer",
        value_fn=lambda data_connection: data_connection["transfers"],
        exists_fn=lambda data_connection: data_connection is not None,
    ),
    SwissPublicTransportSensorEntityDescription(
        key="platform",
        translation_key="platform",
        icon="mdi:bus-stop-uncovered",
        value_fn=lambda data_connection: data_connection["platform"],
        exists_fn=lambda data_connection: data_connection is not None,
    ),
    SwissPublicTransportSensorEntityDescription(
        key="delay",
        translation_key="delay",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.MINUTES,
        icon="mdi:clock-plus",
        value_fn=lambda data_connection: data_connection["delay"],
        exists_fn=lambda data_connection: data_connection is not None,
    ),
)


async def async_setup_entry(
    hass: core.HomeAssistant,
    config_entry: config_entries.ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the sensor from a config entry created in the integrations UI."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id]

    unique_id = config_entry.unique_id

    if TYPE_CHECKING:
        assert unique_id

    async_add_entities(
        SwissPublicTransportSensor(coordinator, description, unique_id)
        for description in SENSORS
    )


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    """Set up the sensor platform."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_IMPORT},
        data=config,
    )
    if (
        result["type"] == FlowResultType.CREATE_ENTRY
        or result["reason"] == "already_configured"
    ):
        async_create_issue(
            hass,
            HOMEASSISTANT_DOMAIN,
            f"deprecated_yaml_{DOMAIN}",
            breaks_in_ha_version="2024.7.0",
            is_fixable=False,
            issue_domain=DOMAIN,
            severity=IssueSeverity.WARNING,
            translation_key="deprecated_yaml",
            translation_placeholders={
                "domain": DOMAIN,
                "integration_title": "Swiss public transport",
            },
        )
    else:
        async_create_issue(
            hass,
            DOMAIN,
            f"deprecated_yaml_import_issue_${result['reason']}",
            breaks_in_ha_version="2024.7.0",
            is_fixable=False,
            issue_domain=DOMAIN,
            severity=IssueSeverity.WARNING,
            translation_key=f"deprecated_yaml_import_issue_${result['reason']}",
            translation_placeholders=PLACEHOLDERS,
        )


class SwissPublicTransportSensor(
    CoordinatorEntity[SwissPublicTransportDataUpdateCoordinator], SensorEntity
):
    """Implementation of a Swiss public transport sensor."""

    entity_description: SwissPublicTransportSensorEntityDescription
    _attr_attribution = "Data provided by transport.opendata.ch"
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: SwissPublicTransportDataUpdateCoordinator,
        entity_description: SwissPublicTransportSensorEntityDescription,
        unique_id: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entity_description = entity_description
        self._attr_unique_id = f"{unique_id}_{self.entity_description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, unique_id)},
            manufacturer="Opendata.ch",
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def enabled(self) -> bool:
        """Enable the sensor if data is available."""
        return self.entity_description.exists_fn(
            self.coordinator.data[self.entity_description.index or 0]
        )

    @property
    def native_value(self) -> datetime | None:
        """Return the state of the sensor."""
        return self.entity_description.value_fn(
            self.coordinator.data[self.entity_description.index or 0]
        )
