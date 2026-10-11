from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional
import requests
import re
import time
from api_logging import logged_request

@dataclass
class WindObs:
    direction_deg: int   # degrees FROM, 0 = variable/calm
    speed_kt: int
    gust_kt: Optional[int]
    raw_metar: str
    observed_at: datetime

_cached_wind: Optional[WindObs] = None
_last_fetch_time: float = 0.0
CACHE_TTL_SEC = 600  # 10 minutes

def parse_metar_wind(raw_metar: str, observed_at: Optional[datetime] = None) -> WindObs:
    """
    Parses wind direction, speed, and gust from a METAR string.
    Example wind tokens: '27012G18KT', '09008KT', 'VRB04KT', '00000KT'
    """
    if observed_at is None:
        observed_at = datetime.now(timezone.utc)

    wind_match = re.search(r'\b(VRB|\d{3})(\d{2,3})(?:G(\d{2,3}))?KT\b', raw_metar)
    if wind_match:
        dir_str, speed_str, gust_str = wind_match.groups()
        dir_deg = 0 if dir_str == "VRB" else int(dir_str)
        speed = int(speed_str)
        gust = int(gust_str) if gust_str else None
        return WindObs(
            direction_deg=dir_deg,
            speed_kt=speed,
            gust_kt=gust,
            raw_metar=raw_metar,
            observed_at=observed_at
        )

    return WindObs(
        direction_deg=0,
        speed_kt=0,
        gust_kt=None,
        raw_metar=raw_metar,
        observed_at=observed_at
    )

def get_wind_kbwi() -> WindObs:
    """Fetches latest KBWI METAR. Returns cached result within 10-min TTL."""
    global _cached_wind, _last_fetch_time
    now = time.time()
    if _cached_wind is not None and (now - _last_fetch_time) < CACHE_TTL_SEC:
        return _cached_wind

    url = "https://aviationweather.gov/api/data/metar?ids=KBWI&format=json"
    try:
        resp = logged_request("Aviation Weather", "GET", url, requests.get, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if data and isinstance(data, list) and len(data) > 0:
            metar_item = data[0]
            raw_metar = metar_item.get("rawOb") or metar_item.get("metar") or ""
            wdir = metar_item.get("wdir")
            wspd = metar_item.get("wspd")
            wgust = metar_item.get("wgust")
            obs_time_val = metar_item.get("obsTime") or metar_item.get("reportTime")

            obs_dt = datetime.now(timezone.utc)
            if obs_time_val:
                try:
                    if isinstance(obs_time_val, (int, float)):
                        obs_dt = datetime.fromtimestamp(obs_time_val, timezone.utc)
                    else:
                        obs_dt = datetime.fromisoformat(str(obs_time_val).replace("Z", "+00:00"))
                except Exception:
                    pass

            if wdir is not None and wspd is not None:
                wind = WindObs(
                    direction_deg=0 if str(wdir) == "VRB" else int(wdir),
                    speed_kt=int(wspd),
                    gust_kt=int(wgust) if wgust is not None else None,
                    raw_metar=raw_metar,
                    observed_at=obs_dt
                )
            else:
                wind = parse_metar_wind(raw_metar, obs_dt)

            _cached_wind = wind
            _last_fetch_time = now
            return wind
    except Exception as e:
        print(f"[Weather] Error fetching METAR: {e}")

    # Return cached if available
    if _cached_wind:
        return _cached_wind

    # Default fallback
    fallback_wind = WindObs(
        direction_deg=0,
        speed_kt=0,
        gust_kt=None,
        raw_metar="METAR UNAVAILABLE",
        observed_at=datetime.now(timezone.utc)
    )
    return fallback_wind
