import math
import re
from opensky_client import StateVector
from config import Settings

def haversine_nm(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calculates the great-circle distance between two points on Earth in Nautical Miles.
    """
    R_NM = 3440.065  # Earth radius in nautical miles
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (math.sin(delta_phi / 2) ** 2 +
         math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R_NM * c

def is_flyover(sv: StateVector, settings: Settings) -> bool:
    """
    Returns True if all conditions met:
      - on_ground == False
      - 500 ft ≤ altitude ≤ 10,000 ft  (departure gate)
      - callsign starts with 3 alpha chars  (commercial heuristic)
      - Haversine distance to listen point ≤ flyover_radius_nm
    """
    if sv.on_ground:
        return False

    if sv.altitude_m is None:
        return False

    altitude_ft = sv.altitude_m * 3.28084
    if not (500 <= altitude_ft <= 10000):
        return False

    callsign = (sv.callsign or "").strip()
    if not re.match(r'^[A-Za-z]{3}', callsign):
        return False

    dist_nm = haversine_nm(sv.latitude, sv.longitude, settings.listen_lat, settings.listen_lon)
    if dist_nm > settings.flyover_radius_nm:
        return False

    return True
