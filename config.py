from dataclasses import dataclass, field
import logging
import os
import math
from pathlib import Path

import folium

from geocoder import geocode_address


LOGGER = logging.getLogger(__name__)

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    # Fallback env file parser if python-dotenv is not installed
    print("[Warning] python-dotenv not installed; falling back to basic .env parsing.")
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                   #os.environ[k.strip()] = v.strip()

# TODO consider the little runway labels like 15L and 33R, which are not in the original BWI runways list.  For now, we will just ignore them.
# 335 is correct see https://marylandaviation.com/environmental/airport-noise/acronyms-faqs-more/   
@dataclass
class Settings:
    opensky_client_id: str
    opensky_client_secret: str
    listen_address: str
    listen_lat: float
    listen_lon: float
    flyover_radius_nm: float
    bbox_padding_nm: float
    bbox: dict
    poll_interval_sec: int
    runways: dict[str, int] = field(default_factory=lambda: {
        "10": 105,
        "28": 285,
        "15R": 155,
        "33L": 335
    })

def compute_bbox(lat: float, lon: float, radius_nm: float, padding_nm: float = 20.0) -> dict:
    total_radius = radius_nm + padding_nm
    print(f"[DEBUG] Computing bbox for lat={lat}, lon={lon}, radius_nm={radius_nm}, padding_nm={padding_nm}, total_radius={total_radius}")
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


# def write_bbox_map(lat: float, lon: float, bbox: dict) -> Path:
#     map_path = Path.cwd() / "bbox_map.html"
#     map_view = folium.Map(location=[lat, lon], zoom_start=11)
#     folium.Rectangle(
#         bounds=[
#             [bbox["lamin"], bbox["lomin"]],
#             [bbox["lamax"], bbox["lomax"]],
#         ],
#         color="blue",
#         fill=True,
#         fill_color="blue",
#         fill_opacity=0.2,
#         popup="OpenSky BBox",
#     ).add_to(map_view)
#     map_view.save(str(map_path))
#     LOGGER.info("OpenSky bounding-box map: %s", map_path.as_uri())
#     return map_path


# def write_bbox_map(lat: float, lon: float, bbox: dict) -> Path:
#     map_path = Path.cwd() / "bbox_map.html"
    
#     # Use CartoDB Positron tiles instead of default OpenStreetMap
#     map_view = folium.Map(
#         location=[lat, lon], 
#         zoom_start=11, 
#         tiles="CartoDB positron"
#     )
    
#     folium.Rectangle(
#         bounds=[
#             [bbox["lamin"], bbox["lomin"]],
#             [bbox["lamax"], bbox["lomax"]],
#         ],
#         color="blue",
#         fill=True,
#         fill_color="blue",
#         fill_opacity=0.2,
#         popup="OpenSky BBox",
#     ).add_to(map_view)
    
#     map_view.save(str(map_path))
#     LOGGER.info("OpenSky bounding-box map: %s", map_path.as_uri())
#     return map_path


def write_bbox_map(lat: float, lon: float, bbox: dict) -> Path:
    map_path = Path.cwd() / "bbox_map.html"
    
    # Use OpenTopoMap tiles (Free, no API key required)
    map_view = folium.Map(
        location=[lat, lon], 
        zoom_start=11, 
        tiles="OpenTopoMap",
        attr="Map data: &copy; OpenStreetMap contributors, SRTM | Map style: &copy; OpenTopoMap (CC-BY-SA)"
    )
    
    folium.Rectangle(
        bounds=[
            [bbox["lamin"], bbox["lomin"]],
            [bbox["lamax"], bbox["lomax"]],
        ],
        color="blue",
        fill=True,
        fill_color="blue",
        fill_opacity=0.2,
        popup="OpenSky BBox",
    ).add_to(map_view)
    
    map_view.save(str(map_path))
    LOGGER.info("OpenSky bounding-box map: %s", map_path.as_uri())
    return map_path

def load_settings() -> Settings:
    client_id = os.getenv("OPENSKY_CLIENT_ID", "")
    client_secret = os.getenv("OPENSKY_CLIENT_SECRET", "")
    address = os.getenv("LISTEN_ADDRESS", "123 Main St, Elkridge, MD 21075")

    try:
        radius_nm = float(os.getenv("FLYOVER_RADIUS_NM", "1.0"))
    except ValueError:
        radius_nm = 1.0

    try:
        bbox_padding_nm = float(os.getenv("BBOX_PADDING_NM", "20.0"))
    except ValueError:
        bbox_padding_nm = 20.0

    try:
        poll_interval_sec = int(os.getenv("POLL_INTERVAL_SEC", "30"))
    except ValueError:
        poll_interval_sec = 30

    lat, lon = geocode_address(address)
    bbox = compute_bbox(lat, lon, radius_nm, bbox_padding_nm)
    write_bbox_map(lat, lon, bbox)
    # log the bbox for debugging purposes witht he padding and radius
    print(f"[DEBUG] Computed bbox: {bbox}")
    print(f"[DEBUG] Bbox parameters - lat: {lat}, lon: {lon}, radius: {radius_nm}, padding: {bbox_padding_nm}")

    return Settings(
        opensky_client_id=client_id,
        opensky_client_secret=client_secret,
        listen_address=address,
        listen_lat=lat,
        listen_lon=lon,
        flyover_radius_nm=radius_nm,
        bbox_padding_nm=bbox_padding_nm,
        bbox=bbox,
        poll_interval_sec=poll_interval_sec
    )
