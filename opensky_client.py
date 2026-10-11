from dataclasses import dataclass
from typing import Optional
import time
import requests
from api_logging import logged_request

@dataclass
class TrackWaypoint:
    timestamp: int       # unix epoch
    latitude: float
    longitude: float
    altitude_m: Optional[float]  # baro altitude in metres; None if unknown
    true_track: Optional[float]  # 0–360°, clockwise from north; None if unknown
    on_ground: bool

@dataclass
class StateVector:
    icao24: str       # hex transponder ID
    callsign: str     # e.g. "SWA1234"
    longitude: float
    latitude: float
    altitude_m: float
    velocity_mps: float
    true_track: float  # 0–360°, clockwise from north
    on_ground: bool
    timestamp: int     # unix epoch

class OpenSkyClient:
    def __init__(self, client_id: str = "", client_secret: str = "", bbox: Optional[dict] = None):
        self.client_id = client_id.strip() if client_id else ""
        self.client_secret = client_secret.strip() if client_secret else ""
        self.bbox = bbox or {}
        self.token: Optional[str] = None
        self.token_expiry: float = 0.0

    def _get_auth_headers(self) -> dict:
        headers = {
            "User-Agent": "bwi-flyover-tracker/1.0"
        }
        if not self.client_id or self.client_id == "your_client_id_here":
            return headers

        now = time.time()
        if self.token and now < self.token_expiry:
            headers["Authorization"] = f"Bearer {self.token}"
            return headers

        # Authenticate via OAuth2 client credentials
        token_url = "https://auth.opensky-network.org/auth/realms/opensky-network/protocol/openid-connect/token"
        data = {
            "grant_type": "client_credentials",
            "client_id": self.client_id,
            "client_secret": self.client_secret
        }
        try:
            resp = logged_request(
                "OpenSky OAuth",
                "POST",
                token_url,
                requests.post,
                data=data,
                timeout=10,
            )
            if resp.status_code == 200:
                token_data = resp.json()
                self.token = token_data.get("access_token")
                expires_in = token_data.get("expires_in", 1800)
                self.token_expiry = now + expires_in - 30
                if self.token:
                    headers["Authorization"] = f"Bearer {self.token}"
            else:
                print(f"[OpenSky] OAuth token request failed ({resp.status_code}): {resp.text[:100]}")
        except Exception as e:
            print(f"[OpenSky] Error requesting OAuth token: {e}")

        return headers

    def fetch(self, bbox: Optional[dict] = None) -> list[StateVector]:
        target_bbox = bbox or self.bbox
        url = "https://opensky-network.org/api/states/all"
        params = {}
        if target_bbox:
            params = {
                "lamin": target_bbox.get("lamin"),
                "lomin": target_bbox.get("lomin"),
                "lamax": target_bbox.get("lamax"),
                "lomax": target_bbox.get("lomax"),
            }

        headers = self._get_auth_headers()
        try:
            print(f"[OpenSky] Fetching states with bbox {params}")
            resp = logged_request(
                "OpenSky states",
                "GET",
                url,
                requests.get,
                params=params,
                headers=headers,
                timeout=15,
            )
            if resp.status_code != 200:
                print(f"[OpenSky] API call returned status {resp.status_code}")
                return []

            data = resp.json()
            states_raw = data.get("states") or []
            api_time = data.get("time", int(time.time()))

            vectors = []
            for s in states_raw:
                if not isinstance(s, list) or len(s) < 11:
                    continue

                icao24 = s[0] or ""
                callsign = (s[1] or "").strip()
                lon = s[5]
                lat = s[6]
                alt = s[7] if s[7] is not None else s[13] # fallback to geo_altitude if baro_altitude is None
                vel = s[9] or 0.0
                track = s[10] or 0.0
                on_ground = bool(s[8])

                if lat is None or lon is None or alt is None:
                    continue

                vectors.append(StateVector(
                    icao24=str(icao24),
                    callsign=str(callsign),
                    longitude=float(lon),
                    latitude=float(lat),
                    altitude_m=float(alt),
                    velocity_mps=float(vel),
                    true_track=float(track),
                    on_ground=on_ground,
                    timestamp=int(api_time)
                ))
            return vectors
        except Exception as e:
            print(f"[OpenSky] Fetch error: {e}")
            return []

    def get_track_by_aircraft(self, icao24: str, at_time: int = 0) -> list[TrackWaypoint]:
        """
        Fetches the historical flight track for a given ICAO24 transponder address.

        Args:
            icao24:  Hex transponder address (e.g. \"a1b2c3\").
            at_time: Optional Unix timestamp.  When 0 (default) the API returns the
                     most-recently-stored track for the aircraft.

        Returns:
            A list of TrackWaypoint objects sorted ascending by timestamp.
            Returns an empty list if the track is unavailable or the request fails.
        """
        url = "https://opensky-network.org/api/tracks/all"
        params: dict = {"icao24": icao24.lower()}
        if at_time:
            params["time"] = at_time

        headers = self._get_auth_headers()
        try:
            resp = logged_request(
                "OpenSky tracks",
                "GET",
                url,
                requests.get,
                params=params,
                headers=headers,
                timeout=15,
            )
            if resp.status_code == 404:
                # Aircraft has no stored track – not an error worth logging
                return []
            if resp.status_code != 200:
                print(f"[OpenSky] get_track_by_aircraft returned {resp.status_code} for {icao24}")
                return []

            data = resp.json()
            raw_path = data.get("path") or []
            waypoints: list[TrackWaypoint] = []
            for point in raw_path:
                # Each element: [time, lat, lon, baro_alt, true_track, on_ground]
                if not isinstance(point, list) or len(point) < 6:
                    continue
                waypoints.append(TrackWaypoint(
                    timestamp=int(point[0]),
                    latitude=float(point[1]) if point[1] is not None else 0.0,
                    longitude=float(point[2]) if point[2] is not None else 0.0,
                    altitude_m=float(point[3]) if point[3] is not None else None,
                    true_track=float(point[4]) if point[4] is not None else None,
                    on_ground=bool(point[5]),
                ))
            # Sort oldest first to make it easy to find the first airborne moment
            waypoints.sort(key=lambda w: w.timestamp)
            return waypoints
        except Exception as e:
            print(f"[OpenSky] get_track_by_aircraft error for {icao24}: {e}")
            return []
