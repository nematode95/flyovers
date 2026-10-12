from __future__ import annotations
import math
from typing import TYPE_CHECKING, Optional, Any, Union

if TYPE_CHECKING:
    from opensky_client import TrackWaypoint

# KBWI Airport Reference Point (ARP)
BWI_ARP_LAT = 39.1754
BWI_ARP_LON = -76.6683

# KBWI Runway Geometry Data (from FAA & AirNav https://www.airnav.com/airport/kbwi)
# Coordinates represent threshold (liftoff/approach start) and opposite end.
# True Headings and Magnetic Headings are exact surveyed specifications.
BWI_RUNWAYS: dict[str, dict[str, Any]] = {
    "10": {
        "name": "10",
        "label": "10 (East)",
        "threshold": (39.174747, -76.689618),
        "far_end": (39.172632, -76.652673),
        "true_heading": 94.0,
        "magnetic_heading": 105,
        "length_ft": 10503,
        "width_ft": 150,
        "is_ga": False,
        "description": "Departures roll east toward Severna Park / Chesapeake Bay",
    },
    "28": {
        "name": "28",
        "label": "28 (West)",
        "threshold": (39.172632, -76.652673),
        "far_end": (39.174747, -76.689618),
        "true_heading": 274.0,
        "magnetic_heading": 285,
        "length_ft": 10503,
        "width_ft": 150,
        "is_ga": False,
        "description": "Departures roll west toward Elkridge / Columbia",
    },
    "15R": {
        "name": "15R",
        "label": "15R (SSE)",
        "threshold": (39.185361, -76.681992),
        "far_end": (39.164203, -76.662393),
        "true_heading": 144.0,
        "magnetic_heading": 155,
        "length_ft": 9501,
        "width_ft": 150,
        "is_ga": False,
        "description": "Departures roll southeast over Anne Arundel Co, often making a climbing right turn west/northwest over Elkridge",
    },
    "33L": {
        "name": "33L",
        "label": "33L (NNW)",
        "threshold": (39.164203, -76.662393),
        "far_end": (39.185361, -76.681992),
        "true_heading": 324.0,
        "magnetic_heading": 335,
        "length_ft": 9501,
        "width_ft": 150,
        "is_ga": False,
        "description": "Departures roll northwest toward Elkridge / Catonsville",
    },
    "15L": {
        "name": "15L",
        "label": "15L (SSE GA)",
        "threshold": (39.187373, -76.663540),
        "far_end": (39.176235, -76.653231),
        "true_heading": 144.0,
        "magnetic_heading": 155,
        "length_ft": 5000,
        "width_ft": 100,
        "is_ga": True,
        "description": "Parallel regional/GA runway pointing southeast",
    },
    "33R": {
        "name": "33R",
        "label": "33R (NNW GA)",
        "threshold": (39.176235, -76.653231),
        "far_end": (39.187373, -76.663540),
        "true_heading": 324.0,
        "magnetic_heading": 335,
        "length_ft": 5000,
        "width_ft": 100,
        "is_ga": True,
        "description": "Parallel regional/GA runway pointing northwest",
    },
}

CARDINAL_DIRECTIONS = [
    "N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
    "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"
]


def heading_to_cardinal(heading: float) -> str:
    """Converts heading in degrees (0-360) to 16-point cardinal direction string."""
    idx = int((heading % 360 + 11.25) // 22.5) % 16
    return CARDINAL_DIRECTIONS[idx]


def angular_difference(deg1: float, deg2: float) -> float:
    """Computes shortest angular difference in degrees between two headings [0, 180]."""
    return abs((deg1 - deg2 + 180) % 360 - 180)


def haversine_nm(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great circle distance between two points in nautical miles."""
    r_nm = 3440.065
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = (math.sin(dphi / 2.0) ** 2 +
         math.cos(phi1) * math.cos(phi2) * (math.sin(dlambda / 2.0) ** 2))
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return r_nm * c


def initial_bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculates initial bearing from (lat1, lon1) to (lat2, lon2) in degrees [0, 360)."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_lambda = math.radians(lon2 - lon1)
    y = math.sin(delta_lambda) * math.cos(phi2)
    x = (math.cos(phi1) * math.sin(phi2) -
         math.sin(phi1) * math.cos(phi2) * math.cos(delta_lambda))
    brng = math.degrees(math.atan2(y, x))
    return (brng + 360.0) % 360.0


def extract_takeoff_heading(track: list[Any]) -> Optional[float]:
    """
    Returns the true_track of the first airborne waypoint in a historical track,
    which is the best available approximation of the actual takeoff heading.
    """
    if not track:
        return None

    for wp in track:
        # Support TrackWaypoint dataclass, dict, or list
        if hasattr(wp, "on_ground"):
            on_ground = wp.on_ground
            track_val = wp.true_track
        elif isinstance(wp, dict):
            on_ground = wp.get("on_ground", False)
            track_val = wp.get("true_track")
        elif isinstance(wp, (list, tuple)) and len(wp) >= 6:
            on_ground = bool(wp[5])
            track_val = float(wp[4]) if wp[4] is not None else None
        else:
            continue

        if not on_ground and track_val is not None:
            return float(track_val)

    return None


def infer_runway(true_track: Optional[float], runways: Optional[dict[str, int]] = None) -> tuple[str, str]:
    """
    Legacy heading-only angular matcher.
    Returns (runway_id, label) e.g. ("28", "28 (West)").
    Tolerance ±20°. Closest angular match wins.
    Falls back to ("UNKNOWN", "Unknown direction").
    """
    if true_track is None or not (0 <= true_track <= 360):
        return ("UNKNOWN", "Unknown direction")

    if runways is None:
        runways = {r_id: r_data["magnetic_heading"] for r_id, r_data in BWI_RUNWAYS.items()}

    best_rwy = None
    best_diff = float("inf")

    for rwy_id, heading in runways.items():
        diff = angular_difference(true_track, heading)
        if diff < best_diff:
            best_diff = diff
            best_rwy = rwy_id

    if best_rwy is not None and best_diff <= 20.0:
        cardinal = heading_to_cardinal(true_track)
        if best_rwy == "28" and cardinal in ("W", "WNW"):
            cardinal_display = "West" if cardinal == "W" else cardinal
        else:
            cardinal_display = cardinal

        label = f"{best_rwy} ({cardinal_display})"
        return (best_rwy, label)

    return ("UNKNOWN", "Unknown direction")


def _extract_pt(pt: Any) -> Optional[dict[str, Any]]:
    """Normalize waypoint representations to standard dict."""
    if hasattr(pt, "latitude"):
        return {
            "lat": pt.latitude,
            "lon": pt.longitude,
            "alt_m": pt.altitude_m or 0.0,
            "track": pt.true_track,
            "on_ground": getattr(pt, "on_ground", False),
            "timestamp": getattr(pt, "timestamp", 0)
        }
    if isinstance(pt, dict):
        return {
            "lat": pt.get("lat", pt.get("latitude")),
            "lon": pt.get("lon", pt.get("longitude")),
            "alt_m": pt.get("altitude_m", pt.get("baro_altitude", 0.0)),
            "track": pt.get("true_track", pt.get("track")),
            "on_ground": pt.get("on_ground", False),
            "timestamp": pt.get("timestamp", pt.get("time", 0))
        }
    if isinstance(pt, (list, tuple)) and len(pt) >= 6:
        return {
            "lat": pt[1],
            "lon": pt[2],
            "alt_m": pt[3] or 0.0,
            "track": pt[4],
            "on_ground": bool(pt[5]),
            "timestamp": pt[0]
        }
    return None


def infer_runway_from_track(
    track: list[Any],
    fallback_heading: Optional[float] = None,
    runways: Optional[dict[str, int]] = None
) -> tuple[str, str, str, Optional[float]]:
    """
    High-accuracy geometric takeoff runway detector using full 6-runway KBWI geometry.

    Evaluates:
      - Along-track takeoff roll vector from threshold
      - Perpendicular cross-track deviation from runway centerline
      - Initial true track alignment
      - Special 15R southeast takeoff + right climbing turn over Elkridge

    Returns:
      (runway_id, runway_label, explanation, takeoff_heading_deg)
      e.g. ("33L", "33L (NNW)", "Liftoff at (39.1904, -76.6874) 0.02 NM from Rwy 33L centerline on heading 310° (runway 324° True / 335° Mag)", 310.0)
    """
    if not track:
        # Fallback to heading-only inference
        rwy_id, label = infer_runway(fallback_heading, runways)
        explanation = (
            f"No track waypoints available; inferred from heading {fallback_heading:.0f}°."
            if fallback_heading is not None else "No track or heading available."
        )
        return (rwy_id, label, explanation, fallback_heading)

    # Normalize waypoints
    normalized = []
    for raw in track:
        p = _extract_pt(raw)
        if p and p["lat"] is not None and p["lon"] is not None:
            normalized.append(p)

    if not normalized:
        rwy_id, label = infer_runway(fallback_heading, runways)
        explanation = f"No valid coordinates in track; inferred from heading {fallback_heading:.0f}°." if fallback_heading else "No coordinates available."
        return (rwy_id, label, explanation, fallback_heading)

    # Filter waypoints within 10 NM of KBWI ARP
    pts_near_bwi = []
    for pt in normalized:
        dist_arp = haversine_nm(pt["lat"], pt["lon"], BWI_ARP_LAT, BWI_ARP_LON)
        if dist_arp <= 10.0:
            pts_near_bwi.append(pt)

    if not pts_near_bwi:
        # Flight does not originate at BWI
        rwy_id, label = infer_runway(fallback_heading, runways)
        p0 = normalized[0]
        p0_dist = haversine_nm(p0["lat"], p0["lon"], BWI_ARP_LAT, BWI_ARP_LON)
        explanation = f"Track originated {p0_dist:.1f} NM from BWI; flight does not appear to depart BWI."
        return (rwy_id, label, explanation, fallback_heading)

    # Identify first airborne point
    airborne_pts = [p for p in pts_near_bwi if not p["on_ground"] and p["track"] is not None]
    target_pt = airborne_pts[0] if airborne_pts else pts_near_bwi[0]

    target_lat = target_pt["lat"]
    target_lon = target_pt["lon"]
    first_alt_ft = target_pt["alt_m"] * 3.28084
    first_on_ground = target_pt["on_ground"]
    takeoff_hdg = target_pt["track"]

    # Only show parens if there was a ground point recorded, otherwise no parens
    target_idx = normalized.index(target_pt) if target_pt in normalized else 0
    has_ground_point = any(p["on_ground"] for p in normalized[:target_idx]) or bool(first_on_ground)
    point_label = "First airborne point (has ground point)" if has_ground_point else "First airborne point"

    # Check for departure turn profiles over Elkridge:
    # 1. Runway 15R / 15L: Departs southeast (~144° True), then executes climbing right turn to NW (~260°-350° True)
    # 2. Runway 10: Departs east (~094° True), then executes climbing turn back to NW/West (~260°-350° True)
    has_se_turn = False
    has_east_turn = False
    tracks_near = [p["track"] for p in pts_near_bwi if p["track"] is not None]
    if len(tracks_near) >= 3:
        has_nw_later = any(260 <= t <= 350 for t in tracks_near[2:])
        if any(120 <= t <= 170 for t in tracks_near[:2]) and has_nw_later:
            has_se_turn = True
        elif any(75 <= t <= 115 for t in tracks_near[:2]) and has_nw_later:
            has_east_turn = True

    scores: dict[str, float] = {}
    details: dict[str, dict[str, Any]] = {}

    for rwy_id, rwy in BWI_RUNWAYS.items():
        th_lat, th_lon = rwy["threshold"]
        fe_lat, fe_lon = rwy["far_end"]
        rwy_hdg = rwy["true_heading"]
        rwy_len_nm = rwy["length_ft"] / 6076.12

        # Along-track and cross-track decomposition from threshold
        d_th = haversine_nm(th_lat, th_lon, target_lat, target_lon)
        brng = initial_bearing_deg(th_lat, th_lon, target_lat, target_lon)

        d_angle = math.radians(brng - rwy_hdg)
        along_track_nm = d_th * math.cos(d_angle)
        cross_track_nm = abs(d_th * math.sin(d_angle))

        track_delta = angular_difference(takeoff_hdg, rwy_hdg) if takeoff_hdg is not None else 45.0

        score = 100.0

        # Cross-track penalty: deviation from extended runway centerline
        if cross_track_nm < 0.1:
            score += 15.0
        elif cross_track_nm < 0.3:
            score += 5.0
        else:
            score -= cross_track_nm * 45.0

        # Along-track alignment: must roll along runway in departure direction
        if along_track_nm < -0.2:
            score -= abs(along_track_nm) * 60.0
        elif 0.0 <= along_track_nm <= rwy_len_nm + 1.5:
            score += 10.0
        else:
            score -= (along_track_nm - (rwy_len_nm + 1.5)) * 12.0

        # Heading alignment and turn bonuses
        if rwy_id in ("15R", "15L") and has_se_turn:
            score += 35.0  # Dominant bonus for matching Runway 15 SE departure with right turn
        elif rwy_id == "10" and has_east_turn:
            score += 35.0  # Dominant bonus for matching Runway 10 East departure with climbing turn
        else:
            if track_delta < 20.0:
                score += 15.0
            elif track_delta < 40.0:
                score += 5.0
            else:
                score -= (track_delta / 180.0) * 50.0

        # Commercial vs GA preference
        if rwy["is_ga"]:
            score -= 15.0

        scores[rwy_id] = max(score, 0.0)
        details[rwy_id] = {
            "along_track_nm": along_track_nm,
            "cross_track_nm": cross_track_nm,
            "track_delta": track_delta,
        }

    # Best runway
    best_rwy_id = max(scores, key=lambda k: scores[k])
    best_rwy = BWI_RUNWAYS[best_rwy_id]
    det = details[best_rwy_id]

    if has_se_turn and best_rwy_id in ("15R", "15L"):
        explanation = (
            f"{point_label} at ({target_lat:.4f}, {target_lon:.4f}) departed Runway {best_rwy['name']} "
            f"southeast on initial heading {tracks_near[0]:.0f}° ({det['cross_track_nm']:.2f} NM from centerline), "
            f"then executed a climbing right turn to {tracks_near[-1]:.0f}° west/northwest over Elkridge."
        )
    elif has_east_turn and best_rwy_id == "10":
        explanation = (
            f"{point_label} at ({target_lat:.4f}, {target_lon:.4f}) departed Runway 10 "
            f"east on initial heading {tracks_near[0]:.0f}° ({det['cross_track_nm']:.2f} NM from centerline), "
            f"then executed a climbing turn back to {tracks_near[-1]:.0f}° west/northwest over Elkridge."
        )
    else:
        hdg_str = f"heading {takeoff_hdg:.0f}°" if takeoff_hdg is not None else "unknown heading"
        explanation = (
            f"{point_label} at ({target_lat:.4f}, {target_lon:.4f}) is {det['cross_track_nm']:.2f} NM from Runway {best_rwy['name']} "
            f"centerline on {hdg_str} (runway heading: {best_rwy['true_heading']:.0f}° True / {best_rwy['magnetic_heading']}° Mag)."
        )

    return (best_rwy_id, best_rwy["label"], explanation, takeoff_hdg)
