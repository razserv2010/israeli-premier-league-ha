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
                f"{API_BASE_URL}/eventsnextleague.php?id={LEAGUE_ID}",
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
        """Fetch scheduled upcoming league fixtures only.

        Uses the dedicated next-league endpoint so we do not issue one request
        per calendar day. On TheSportsDB free API this may return only the next
        event, but it keeps API usage extremely low and avoids rate limiting.
        """
        now = datetime.now(IL_TZ)

        try:
            async with self._session.get(
                f"{API_BASE_URL}/eventsnextleague.php?id={LEAGUE_ID}",
                timeout=aiohttp.ClientTimeout(total=20),
            ) as resp:
                if resp.status != 200:
                    raise UpdateFailed(
                        f"TheSportsDB returned HTTP {resp.status} for upcoming fixtures"
                    )
                data = await resp.json(content_type=None)
        except (aiohttp.ClientError, TimeoutError) as err:
            raise UpdateFailed(f"Error fetching upcoming fixtures: {err}") from err

        results = []
        seen_ids = set()
        for event in data.get("events") or []:
            parsed = self._parse_event(event)
            if not parsed:
                continue
            fixture_id = parsed["fixture_id"]
            if fixture_id in seen_ids:
                continue
            # Schedule only: do not poll live status/results. Keep only matches
            # that have not started yet.
            if parsed["match_datetime"] < now:
                continue
            seen_ids.add(fixture_id)
            results.append(parsed)

        results.sort(key=lambda item: item["match_datetime"])
        return results

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
