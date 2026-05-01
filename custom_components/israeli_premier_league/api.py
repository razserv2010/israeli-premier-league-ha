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

IL_TZ = timezone(timedelta(hours=3))

class IsraeliPremierLeagueAPI:
    def __init__(self, hass: HomeAssistant) -> None:
        self._hass = hass
        self._session = async_get_clientsession(hass)

    async def async_validate(self) -> bool:
        try:
            async with self._session.get(
                f"{API_BASE_URL}/eventsday.php?d=2025-01-01&l={LEAGUE_ID}",
                timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                return resp.status == 200
        except Exception as err:
            _LOGGER.error("Connection error: %s", err)
        return False

    async def async_get_fixtures(self) -> list[dict]:
        now = datetime.now(IL_TZ)
        results = []
        seen_ids = set()

        for day_offset in range(DAYS_AHEAD + 1):
            day = now + timedelta(days=day_offset)
            date_str = day.strftime("%Y-%m-%d")

            try:
                async with self._session.get(
                    f"{API_BASE_URL}/eventsday.php?d={date_str}&l={LEAGUE_ID}",
                    timeout=aiohttp.ClientTimeout(total=15)
                ) as resp:
                    if resp.status != 200:
                        continue
                    data = await resp.json(content_type=None)
            except aiohttp.ClientError as err:
                _LOGGER.warning("Error fetching day %s: %s", date_str, err)
                continue

            for event in (data.get("events") or []):
                parsed = self._parse_event(event)
                if parsed and parsed["fixture_id"] not in seen_ids:
                    seen_ids.add(parsed["fixture_id"])
                    results.append(parsed)

        results.sort(key=lambda x: x["match_datetime"])
        return results

    def _parse_event(self, event: dict) -> dict | None:
        try:
            date_str = event.get("dateEvent", "")
            time_str = event.get("strTime", "00:00:00") or "00:00:00"
            # TheSportsDB מחזיר שעות ב-UTC — מוסיפים 3 שעות לשעון ישראל
            dt_utc = datetime.strptime(f"{date_str} {time_str[:5]}", "%Y-%m-%d %H:%M")
            dt_utc = dt_utc.replace(tzinfo=timezone.utc)
            il_time = dt_utc.astimezone(IL_TZ)
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
            "channels": "ספורט 1 / ספורט 2 / ONE",
        }
