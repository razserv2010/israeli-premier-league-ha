"""API client for Israeli Premier League (api-sports.io)."""
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
    def __init__(self, hass: HomeAssistant, api_key: str) -> None:
        self._hass = hass
        self._api_key = api_key
        self._session = async_get_clientsession(hass)

    @property
    def _headers(self) -> dict:
        return {"x-apisports-key": self._api_key, "Accept": "application/json"}

    async def async_validate_key(self) -> bool:
        try:
            async with self._session.get(
                f"{API_BASE_URL}/status", headers=self._headers,
                timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get("response", {}).get("requests", {}).get("current", -1) >= 0
        except Exception as err:
            _LOGGER.error("Error validating API key: %s", err)
        return False

    async def async_get_fixtures(self) -> list[dict]:
        now = datetime.now(timezone.utc)

        # עונת כדורגל: אוגוסט-יולי. אם לפני אוגוסט — העונה התחילה אשתקד
        season = now.year if now.month >= 8 else now.year - 1

        params = {
            "league": LEAGUE_ID,
            "season": season,
            "from": now.strftime("%Y-%m-%d"),
            "to": (now + timedelta(days=DAYS_AHEAD)).strftime("%Y-%m-%d"),
            "timezone": "Asia/Jerusalem",
        }
        try:
            async with self._session.get(
                f"{API_BASE_URL}/fixtures", headers=self._headers, params=params,
                timeout=aiohttp.ClientTimeout(total=15)
            ) as resp:
                if resp.status != 200:
                    raise UpdateFailed(f"API returned status {resp.status}")
                data = await resp.json()
        except aiohttp.ClientError as err:
            raise UpdateFailed(f"Network error: {err}") from err

        results = [self._parse_fixture(f) for f in data.get("response", [])]
        results.sort(key=lambda x: x["match_datetime"])
        return results

    def _parse_fixture(self, fixture: dict) -> dict:
        f = fixture.get("fixture", {})
        teams = fixture.get("teams", {})
        goals = fixture.get("goals", {})
        league = fixture.get("league", {})
        dt_str = f.get("date", "")
        try:
            match_dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
            il_time = match_dt.astimezone(timezone(timedelta(hours=3)))
            date_str = il_time.strftime("%d/%m/%Y")
            time_str = il_time.strftime("%H:%M")
        except Exception:
            date_str = dt_str[:10]
            time_str = ""
            il_time = datetime.min.replace(tzinfo=timezone.utc)

        status_map = {
            "NS": "לא התחיל", "1H": "מחצית ראשונה", "HT": "הפסקה",
            "2H": "מחצית שנייה", "ET": "הארכה", "P": "פנדלים",
            "FT": "הסתיים", "AET": "הסתיים (הארכה)", "PEN": "הסתיים (פנדלים)",
            "PST": "נדחה", "CANC": "בוטל", "TBD": "לא נקבע",
        }
        status = f.get("status", {}).get("short", "NS")
        return {
            "fixture_id": f.get("id"),
            "match_datetime": il_time,
            "match_date": date_str,
            "match_time": time_str,
            "home_team": teams.get("home", {}).get("name", ""),
            "away_team": teams.get("away", {}).get("name", ""),
            "home_logo": teams.get("home", {}).get("logo", ""),
            "away_logo": teams.get("away", {}).get("logo", ""),
            "home_score": goals.get("home"),
            "away_score": goals.get("away"),
            "status": status_map.get(status, status),
            "status_short": status,
            "venue": f.get("venue", {}).get("name", ""),
            "round": league.get("round", ""),
            "channels": ["ספורט 1", "ספורט 2", "ONE"],
        }
