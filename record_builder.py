from dataclasses import dataclass, asdict
from datetime import datetime
import json
from typing import Optional
from opensky_client import StateVector
from weather_client import WindObs
from flight_enricher import FlightEnrichment

@dataclass
class FlyoverRecord:
    timestamp: str         # ISO 8601 local time
    flight_number: str     # callsign, e.g. "SWA1234"
    icao24: str
    aircraft_type: str     # e.g. "B738" or "UNKNOWN"
    aircraft_model: str    # e.g. "Boeing 737-800" or "Unknown Aircraft"
    destination: str       # e.g. "FLL" or "UNKNOWN"
    route: str             # e.g. "BWI ⟶ FLL" or "Unknown Route"
    altitude_ft: int
    flyover_track_deg: float         # heading observed at flyover (live)
    takeoff_heading_deg: Optional[float]  # first-airborne heading from historical track
    heading_source: str              # "historical_track" | "flyover_fallback"
    runway: str            # "28", "33L", or "UNKNOWN"
    runway_direction: str  # "28 (West)", "33L (NNW)", etc.
    wind_direction_deg: int
    wind_speed_kt: int
    wind_gust_kt: Optional[int]
    raw_metar: str

def build(
    sv: StateVector,
    runway: str,
    runway_direction: str,
    wind: WindObs,
    enrichment: Optional[FlightEnrichment] = None,
    takeoff_heading_deg: Optional[float] = None,
    heading_source: str = "flyover_fallback",
) -> FlyoverRecord:
    """
    Builds a FlyoverRecord instance from state vector, runway inference, wind observation,
    and optional flight enrichment data.

    Args:
        sv:                 Live state vector captured at flyover time.
        runway:             Inferred runway ID (e.g. "28").
        runway_direction:   Human-readable runway label (e.g. "28 (West)").
        wind:               Wind observation from KBWI METAR.
        enrichment:         Optional flight enrichment (aircraft type, route, etc.).
        takeoff_heading_deg: The heading at the first airborne waypoint from the
                             historical track, if successfully retrieved.
        heading_source:     "historical_track" when takeoff_heading_deg came from the
                            API; "flyover_fallback" when the live flyover heading was
                            used instead.
    """
    local_now = datetime.now().astimezone()
    timestamp_str = local_now.isoformat(timespec='seconds')

    altitude_ft = int(round(sv.altitude_m * 3.28084))
    flyover_track = round(float(sv.true_track), 1)

    ac_type = enrichment.aircraft_type if enrichment else "UNKNOWN"
    ac_model = enrichment.aircraft_model if enrichment else "Unknown Aircraft"
    dest = enrichment.destination if enrichment else "UNKNOWN"
    route_str = enrichment.route if enrichment else "Unknown Route"

    return FlyoverRecord(
        timestamp=timestamp_str,
        flight_number=(sv.callsign or "").strip(),
        icao24=sv.icao24,
        aircraft_type=ac_type,
        aircraft_model=ac_model,
        destination=dest,
        route=route_str,
        altitude_ft=altitude_ft,
        flyover_track_deg=flyover_track,
        takeoff_heading_deg=round(takeoff_heading_deg, 1) if takeoff_heading_deg is not None else None,
        heading_source=heading_source,
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
