import requests

def geocode_address(address: str) -> tuple[float, float]:
    """
    Calls Nominatim → returns (lat, lon).
    User-Agent: 'bwi-flyover-tracker/1.0' (required by OSM policy).
    Raises ValueError with a clear message if address cannot be resolved.
    """
    if not address or not address.strip():
        raise ValueError("Address cannot be empty.")

    url = "https://nominatim.openstreetmap.org/search"
    headers = {
        "User-Agent": "bwi-flyover-tracker/1.0 (https://github.com/bwi-flyover-tracker)"
    }
    params = {
        "q": address,
        "format": "json",
        "limit": 1
    }
    try:
        response = requests.get(url, headers=headers, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        if not data or len(data) == 0:
            raise ValueError(f"Could not resolve coordinates for address: '{address}'")
        lat = float(data[0]["lat"])
        lon = float(data[0]["lon"])
        return lat, lon
    except requests.RequestException as e:
        raise ValueError(f"Geocoding network error for address '{address}': {e}") from e
    except (KeyError, TypeError, ValueError) as e:
        if isinstance(e, ValueError) and "Could not resolve" in str(e):
            raise
        raise ValueError(f"Failed to parse geocoding response for address '{address}': {e}") from e
