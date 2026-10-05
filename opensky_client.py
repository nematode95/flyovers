from dataclasses import dataclass
from typing import Optional
import time
import requests

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
            resp = requests.post(token_url, data=data, timeout=10)
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
            resp = requests.get(url, params=params, headers=headers, timeout=15)
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
