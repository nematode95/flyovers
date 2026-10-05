from dataclasses import dataclass, field
import os
import math
from geocoder import geocode_address

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    # Fallback env file parser if python-dotenv is not installed
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())

@dataclass
class Settings:
    opensky_client_id: str
    opensky_client_secret: str
    listen_address: str
    listen_lat: float
    listen_lon: float
    flyover_radius_nm: float
    bbox: dict
    poll_interval_sec: int
    runways: dict[str, int] = field(default_factory=lambda: {
        "10": 105,
        "28": 285,
        "15R": 155,
        "33L": 335
    })

def compute_bbox(lat: float, lon: float, radius_nm: float, padding_nm: float = 5.0) -> dict:
    total_radius = radius_nm + padding_nm
    # 1 nm latitude ≈ 1/60°
    lat_delta = total_radius / 60.0
    # 1 nm longitude ≈ 1 / (60 * cos(lat))
    cos_lat = math.cos(math.radians(lat))
    lon_delta = total_radius / (60.0 * cos_lat) if cos_lat != 0 else total_radius / 60.0

    return {
        "lamin": round(lat - lat_delta, 4),
        "lomin": round(lon - lon_delta, 4),
        "lamax": round(lat + lat_delta, 4),
        "lomax": round(lon + lon_delta, 4),
    }

def load_settings() -> Settings:
    client_id = os.getenv("OPENSKY_CLIENT_ID", "")
    client_secret = os.getenv("OPENSKY_CLIENT_SECRET", "")
    address = os.getenv("LISTEN_ADDRESS", "123 Main St, Elkridge, MD 21075")

    try:
        radius_nm = float(os.getenv("FLYOVER_RADIUS_NM", "1.0"))
    except ValueError:
        radius_nm = 1.0

    try:
        poll_interval_sec = int(os.getenv("POLL_INTERVAL_SEC", "30"))
    except ValueError:
        poll_interval_sec = 30

    lat, lon = geocode_address(address)
    bbox = compute_bbox(lat, lon, radius_nm)

    return Settings(
        opensky_client_id=client_id,
        opensky_client_secret=client_secret,
        listen_address=address,
        listen_lat=lat,
        listen_lon=lon,
        flyover_radius_nm=radius_nm,
        bbox=bbox,
        poll_interval_sec=poll_interval_sec
    )
