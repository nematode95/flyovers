CARDINAL_DIRECTIONS = [
    "N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
    "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"
]

def heading_to_cardinal(heading: float) -> str:
    """
    Converts heading in degrees (0-360) to 16-point cardinal direction string.
    """
    idx = int((heading % 360 + 11.25) // 22.5) % 16
    return CARDINAL_DIRECTIONS[idx]

def angular_difference(deg1: float, deg2: float) -> float:
    """
    Computes shortest angular difference in degrees between two headings.
    """
    return abs((deg1 - deg2 + 180) % 360 - 180)

def infer_runway(true_track: float, runways: dict[str, int]) -> tuple[str, str]:
    """
    Returns (runway_id, label) e.g. ("28", "28 (West)").
    Tolerance ±20°. Closest angular match wins.
    Falls back to ("UNKNOWN", "Unknown direction").
    """
    if true_track is None or not (0 <= true_track <= 360):
        return ("UNKNOWN", "Unknown direction")

    best_rwy = None
    best_diff = float("inf")

    for rwy_id, heading in runways.items():
        diff = angular_difference(true_track, heading)
        if diff < best_diff:
            best_diff = diff
            best_rwy = rwy_id

    if best_rwy is not None and best_diff <= 20.0:
        # If runway 28 heading is 285 and track is around 280-285, cardinal can be West or WNW
        # Custom mapping fallback for BWI primary runways for clean human labels if desired:
        cardinal = heading_to_cardinal(true_track)
        # For runway 28 at 285° if cardinal is WNW, "West" or "WNW" is valid
        if best_rwy == "28" and cardinal in ("W", "WNW"):
            # If spec example specifically calls runway 28 "West" or "WNW"
            cardinal_display = "West" if cardinal == "W" else cardinal
        else:
            cardinal_display = cardinal

        label = f"{best_rwy} ({cardinal_display})"
        return (best_rwy, label)

    return ("UNKNOWN", "Unknown direction")
