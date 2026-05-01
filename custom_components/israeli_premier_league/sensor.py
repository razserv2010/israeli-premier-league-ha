"""Sensor platform for Israeli Premier League."""
from __future__ import annotations
import logging
from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    entities = [IsraeliPremierLeagueSummary(coordinator, entry)]
    if coordinator.data:
        for idx in range(min(len(coordinator.data), 10)):
            entities.append(IsraeliPremierLeagueFixtureSensor(coordinator, entry, idx))
    async_add_entities(entities, update_before_add=True)

class IsraeliPremierLeagueSummary(CoordinatorEntity, SensorEntity):
    def __init__(self, coordinator, entry):
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_summary"
        self._attr_name = "ליגת העל - משחקים קרובים"
        self._attr_icon = "mdi:soccer"

    @property
    def native_value(self):
        return len(self.coordinator.data) if self.coordinator.data else 0

    @property
    def extra_state_attributes(self):
        if not self.coordinator.data:
            return {}
        return {"fixtures": [
            {k: f[k] for k in [
                "fixture_id", "home_team", "away_team", "home_logo", "away_logo",
                "match_date", "match_time", "status", "status_short",
                "venue", "channels", "round", "home_score", "away_score"
            ]} for f in self.coordinator.data
        ]}

class IsraeliPremierLeagueFixtureSensor(CoordinatorEntity, SensorEntity):
    def __init__(self, coordinator, entry, index):
        super().__init__(coordinator)
        self._index = index
        self._attr_unique_id = f"{entry.entry_id}_fixture_{index}"
        self._attr_icon = "mdi:soccer-field"

    @property
    def _fixture(self):
        if self.coordinator.data and self._index < len(self.coordinator.data):
            return self.coordinator.data[self._index]
        return None

    @property
    def name(self):
        f = self._fixture
        return f"ליגת העל - {f['home_team']} נגד {f['away_team']}" if f else f"ליגת העל - משחק {self._index+1}"

    @property
    def native_value(self):
        f = self._fixture
        if not f:
            return None
        if f["status_short"] in ("1H", "HT", "2H", "ET", "P"):
            return f"{f['home_score'] or 0}:{f['away_score'] or 0}"
        return f["match_time"]

    @property
    def extra_state_attributes(self):
        f = self._fixture
        if not f:
            return {}
        return {k: f[k] for k in [
            "fixture_id", "home_team", "away_team", "home_logo", "away_logo",
            "match_date", "match_time", "status", "status_short",
            "venue", "channels", "round", "home_score", "away_score"
        ]}
