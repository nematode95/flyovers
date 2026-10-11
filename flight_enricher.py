from dataclasses import dataclass
from typing import Optional
import requests
from api_logging import logged_request

@dataclass
class FlightEnrichment:
    aircraft_type: str     # e.g. "B738" or "UNKNOWN"
    aircraft_model: str    # e.g. "Boeing 737-800" or "Unknown Aircraft"
    destination: str       # e.g. "FLL" or "UNKNOWN"
    route: str             # e.g. "BWI ⟶ FLL" or "Unknown Route"

def get_aircraft_info(icao24: str) -> tuple[str, str]:
    """
    Looks up aircraft type code and model description by 24-bit transponder hex code (icao24).
    Returns (aircraft_type, aircraft_model).
    """
    if not icao24 or not icao24.strip():
        return ("UNKNOWN", "Unknown Aircraft")

    hex_code = icao24.strip().upper()
    url = f"https://hexdb.io/api/v1/aircraft/{hex_code}"
    headers = {
        "User-Agent": "bwi-flyover-tracker/1.0 (https://github.com/bwi-flyover-tracker)"
    }
    try:
        resp = logged_request("HexDB aircraft lookup", "GET", url, requests.get, headers=headers, timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            ac_type = data.get("ICAOTypeCode") or data.get("Type") or "UNKNOWN"
            mfr = data.get("Manufacturer") or ""
            model_name = data.get("Type") or ""
            
            if mfr and model_name:
                ac_model = f"{mfr} {model_name}".strip()
            elif model_name:
                ac_model = model_name
            elif mfr:
                ac_model = mfr
            else:
                ac_model = "Unknown Aircraft"
                
            return (str(ac_type), str(ac_model))
    except Exception as e:
        pass

    return ("UNKNOWN", "Unknown Aircraft")

def get_route_info(callsign: str) -> tuple[str, str]:
    """
    Looks up destination airport and route info by callsign.
    Returns (destination, route).
    """
    cs = (callsign or "").strip()
    if not cs:
        return ("UNKNOWN", "Unknown Route")

    url = f"https://www.flightradar24.com/v1/search/web/find?query={cs}&limit=1"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    try:
        resp = logged_request("FlightRadar24 route lookup", "GET", url, requests.get, headers=headers, timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            results = data.get("results") or []
            if results:
                item = results[0]
                detail = item.get("detail") or {}
                dest = detail.get("schd_to") or detail.get("dest") or "UNKNOWN"
                origin = detail.get("schd_from") or detail.get("origin") or "BWI"
                route_str = detail.get("route")
                if not route_str and dest != "UNKNOWN":
                    route_str = f"{origin} ⟶ {dest}"
                elif not route_str:
                    route_str = "Unknown Route"
                
                return (str(dest), str(route_str))
    except Exception as e:
        pass

    return ("UNKNOWN", "Unknown Route")

def enrich_flight(icao24: str, callsign: str) -> FlightEnrichment:
    """
    Enriches flight vector with aircraft type details and destination route info.
    """
    ac_type, ac_model = get_aircraft_info(icao24)
    dest, route = get_route_info(callsign)
    return FlightEnrichment(
        aircraft_type=ac_type,
        aircraft_model=ac_model,
        destination=dest,
        route=route
    )
