"""API client for Israeli Premier League (TheSportsDB)."""
from __future__ import annotations
import logging
from datetime import datetime, timedelta, timezone
import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import UpdateFailed
from .const import API_BASE_URL, LEAGUE_ID, DAYS_AHEAD

_LOGGER = logging.getLogger(__name__)

class IsraeliPremierLeagueAPI:
    def __init__(self, hass: HomeAssistant) -> None:
        self._hass = hass
        self._session = async_get_clientsession(hass)

    async def async_validate(self) -> bool:
        try:
            async with self._session.get(
                f"{API_BASE_URL}/eventsnextleague.php?id={LEAGUE_ID}",
                timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                return resp.status == 200
        except Exception as err:
            _LOGGER.error("Connection error: %s", err)
        return False

    async def async_get_fixtures(self) -> list[dict]:
        now = datetime.now(timezone(timedelta(hours=3)))
        cutoff = now + timedelta(days=DAYS_AHEAD)

        try:
            async with self._session.get(
                f"{API_BASE_URL}/eventsnextleague.php?id={LEAGUE_ID}",
                timeout=aiohttp.ClientTimeout(total=15)
            ) as resp:
                if resp.status != 200:
                    raise UpdateFailed(f"API returned status {resp.status}")
                data = await resp.json(content_type=None)
        except aiohttp.ClientError as err:
            raise UpdateFailed(f"Network error: {err}") from err

        events = data.get("events") or []
        results = []
        for event in events:
            parsed = self._parse_event(event)
            if parsed and parsed["match_datetime"] <= cutoff:
                results.append(parsed)

        results.sort(key=lambda x: x["match_datetime"])
        return results

    def _parse_event(self, event: dict) -> dict | None:
        try:
            date_str = event.get("dateEvent", "")
            time_str = event.get("strTime", "00:00:00") or "00:00:00"
            dt = datetime.strptime(f"{date_str} {time_str[:5]}", "%Y-%m-%d %H:%M")
            il_time = dt.replace(tzinfo=timezone(timedelta(hours=3)))
        except Exception:
            return None

        status_raw = event.get("strStatus") or "NS"
        status_map = {
            "NS": "לא התחיל",
            "Match Finished": "הסתיים",
            "Half Time": "הפסקה",
            "In Progress": "במהלך",
            "Postponed": "נדחה",
            "Cancelled": "בוטל",
        }

        return {
            "fixture_id": event.get("idEvent"),
            "match_datetime": il_time,
            "match_date": il_time.strftime("%d/%m/%Y"),
            "match_time": il_time.strftime("%H:%M"),
            "home_team": event.get("strHomeTeam", ""),
            "away_team": event.get("strAwayTeam", ""),
            "home_logo": event.get("strHomeTeamBadge", ""),
            "away_logo": event.get("strAwayTeamBadge", ""),
            "home_score": event.get("intHomeScore"),
            "away_score": event.get("intAwayScore"),
            "status": status_map.get(status_raw, status_raw),
            "status_short": status_raw,
            "venue": event.get("strVenue", ""),
            "round": event.get("intRound", ""),
            "channels": event.get("strTVStation", "") or "ספורט 1 / ONE",
        }
