from dataclasses import dataclass, asdict
from datetime import datetime
import json
from typing import Optional
from opensky_client import StateVector
from weather_client import WindObs

@dataclass
class FlyoverRecord:
    timestamp: str         # ISO 8601 local time
    flight_number: str     # callsign, e.g. "SWA1234"
    icao24: str
    altitude_ft: int
    true_track_deg: float
    runway: str            # "28", "33L", or "UNKNOWN"
    runway_direction: str  # "28 (West)", "33L (NNW)", etc.
    wind_direction_deg: int
    wind_speed_kt: int
    wind_gust_kt: Optional[int]
    raw_metar: str

def build(sv: StateVector, runway: str, runway_direction: str, wind: WindObs) -> FlyoverRecord:
    """
    Builds a FlyoverRecord instance from state vector, runway inference, and wind observation.
    """
    local_now = datetime.now().astimezone()
    timestamp_str = local_now.isoformat(timespec='seconds')

    altitude_ft = int(round(sv.altitude_m * 3.28084))
    true_track = round(float(sv.true_track), 1)

    return FlyoverRecord(
        timestamp=timestamp_str,
        flight_number=(sv.callsign or "").strip(),
        icao24=sv.icao24,
        altitude_ft=altitude_ft,
        true_track_deg=true_track,
        runway=runway,
        runway_direction=runway_direction,
        wind_direction_deg=wind.direction_deg,
        wind_speed_kt=wind.speed_kt,
        wind_gust_kt=wind.gust_kt,
        raw_metar=wind.raw_metar
    )

def to_json_line(record: FlyoverRecord) -> str:
    """Serializes to a single JSON line for appending to flyovers.jsonl."""
    return json.dumps(asdict(record))
