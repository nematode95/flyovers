from datetime import datetime
from record_builder import FlyoverRecord, to_json_line

def format_timestamp(iso_str: str) -> str:
    try:
        dt = datetime.fromisoformat(iso_str)
        tz_name = dt.tzname() or ""
        return f"{dt.strftime('%Y-%m-%d %H:%M:%S')} {tz_name}".strip()
    except Exception:
        return iso_str

def print_and_log(record: FlyoverRecord, velocity_mps: float = 0.0, log_file: str = "flyovers.jsonl") -> None:
    """
    Prints a formatted human-readable block to stdout and appends JSON line to flyovers.jsonl.
    """
    json_line = to_json_line(record)
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(json_line + "\n")

    speed_kt = int(round(velocity_mps * 1.94384)) if velocity_mps else 0
    formatted_ts = format_timestamp(record.timestamp)
    
    if record.wind_gust_kt:
        wind_str = f"{record.wind_direction_deg}° at {record.wind_speed_kt} kt, gusting {record.wind_gust_kt} kt"
    else:
        wind_str = f"{record.wind_direction_deg}° at {record.wind_speed_kt} kt"

    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(f"✈  {record.flight_number:<16} {formatted_ts}")
    print(f"   Altitude  : {record.altitude_ft:,} ft  |  Speed: {speed_kt} kt")
    print(f"   Heading   : {int(round(record.true_track_deg))}°")
    print(f"   Runway    : {record.runway_direction}")
    print(f"   Wind      : {wind_str}")
    print(f"   METAR     : {record.raw_metar}")
    print(f"   Logged to : {log_file}")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
