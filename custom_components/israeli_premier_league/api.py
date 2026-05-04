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

TEAM_NAMES_HE = {
    "Maccabi Tel Aviv": "מכבי תל אביב",
    "Maccabi Haifa": "מכבי חיפה",
    "Hapoel Tel Aviv": "הפועל תל אביב",
    "Hapoel Tel-Aviv": "הפועל תל אביב",
    "Hapoel Beer Sheva": "הפועל באר שבע",
    "Hapoel Be'er Sheva": "הפועל באר שבע",
    "Hapoel Haifa": "הפועל חיפה",
    "Beitar Jerusalem": "בית\"ר ירושלים",
    "Hapoel Jerusalem": "הפועל ירושלים",
    "Maccabi Netanya": "מכבי נתניה",
    "Maccabi Bnei Raina": "מכבי בני ריינה",
    "Bnei Sakhnin": "בני סכנין",
    "Hapoel Petah Tikva": "הפועל פתח תקווה",
    "Ironi Kiryat Shmona": "עירוני קרית שמונה",
    "Hapoel Ironi Kiryat Shmona": "הפועל עירוני קרית שמונה",
    "MS Ashdod": "מ.ס. אשדוד",
    "FC Ashdod": "מ.ס. אשדוד",
    "Ironi Tiberias": "עירוני טבריה",
    "Hapoel Nof HaGalil": "הפועל נוף הגליל",
    "Maccabi Petah Tikva": "מכבי פתח תקווה",
    "Hapoel Hadera": "הפועל חדרה",
}

FINISHED_STATUSES = {"Match Finished", "FT", "AET", "PEN"}
LIVE_STATUSES = {"1H", "2H", "HT", "ET", "P", "Halftime", "In Progress"}

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

    async def async_get_real_status(self, fixture_id: str) -> str | None:
        """משוך סטטוס אמיתי של משחק מ-lookupevent."""
        try:
            async with self._session.get(
                f"{API_BASE_URL}/lookupevent.php?id={fixture_id}",
                timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json(content_type=None)
                events = data.get("events") or []
                if events:
                    return events[0].get("strStatus")
        except Exception as err:
            _LOGGER.debug("Error fetching status for %s: %s", fixture_id, err)
        return None

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

        # לכל משחק שהתחיל — בדוק סטטוס אמיתי מ-lookupevent
        updated = []
        for f in results:
            if f["match_datetime"] <= now:
                real_status = await self.async_get_real_status(f["fixture_id"])
                if real_status:
                    if real_status in FINISHED_STATUSES:
                        # משחק הסתיים — הסתר אותו
                        _LOGGER.debug("Hiding finished match: %s vs %s", f["home_team"], f["away_team"])
                        continue
                    # עדכן סטטוס אמיתי
                    f["status_short"] = real_status
                    f["status"] = self._status_map().get(real_status, real_status)
            updated.append(f)

        return updated

    def _status_map(self) -> dict:
        return {
            "NS": "לא התחיל",
            "Match Finished": "הסתיים",
            "Halftime": "הפסקה",
            "HT": "הפסקה",
            "In Progress": "במהלך",
            "1H": "מחצית ראשונה",
            "2H": "מחצית שנייה",
            "ET": "הארכה",
            "P": "פנדלים",
            "FT": "הסתיים",
            "AET": "הסתיים (הארכה)",
            "PEN": "הסתיים (פנדלים)",
            "Postponed": "נדחה",
            "Cancelled": "בוטל",
        }

    def _translate_team(self, name: str) -> str:
        return TEAM_NAMES_HE.get(name, name)

    def _parse_event(self, event: dict) -> dict | None:
        try:
            date_str = event.get("dateEvent", "")
            time_str = event.get("strTime", "00:00:00") or "00:00:00"
            dt_utc = datetime.strptime(f"{date_str} {time_str[:5]}", "%Y-%m-%d %H:%M")
            dt_utc = dt_utc.replace(tzinfo=timezone.utc)
            il_time = dt_utc.astimezone(IL_TZ)
        except Exception:
            return None

        status_raw = event.get("strStatus") or "NS"

        home_en = event.get("strHomeTeam", "")
        away_en = event.get("strAwayTeam", "")

        return {
            "fixture_id": event.get("idEvent"),
            "match_datetime": il_time,
            "match_date": il_time.strftime("%d/%m/%Y"),
            "match_time": il_time.strftime("%H:%M"),
            "home_team": self._translate_team(home_en),
            "away_team": self._translate_team(away_en),
            "home_team_en": home_en,
            "away_team_en": away_en,
            "home_logo": event.get("strHomeTeamBadge", ""),
            "away_logo": event.get("strAwayTeamBadge", ""),
            "home_score": event.get("intHomeScore"),
            "away_score": event.get("intAwayScore"),
            "status": self._status_map().get(status_raw, status_raw),
            "status_short": status_raw,
            "venue": event.get("strVenue", ""),
            "round": event.get("intRound", ""),
            "channels": "ספורט 1 / ספורט 2 / ONE",
        }
