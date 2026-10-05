import time
from config import load_settings
from opensky_client import OpenSkyClient
import flyover_detector
import runway_inferrer
import weather_client
import flight_enricher
import record_builder
import printer

def main():
    try:
        settings = load_settings()
    except Exception as e:
        print(f"[Error] Failed to initialize configuration: {e}")
        return

    print("BWI Flyover Tracker")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(f"Listening at : {settings.listen_address}")
    print(f"Coordinates  : {settings.listen_lat:.5f}°N, {abs(settings.listen_lon):.5f}°W")
    print(f"Radius       : {settings.flyover_radius_nm} nm (~{settings.flyover_radius_nm * 1.15:.2f} miles)")
    print(f"Poll interval: {settings.poll_interval_sec}s")
    print("Log file     : flyovers.jsonl")
    runway_str = ", ".join(f"{k} ({v}°)" for k, v in settings.runways.items())
    print(f"Runways      : {runway_str}")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("Waiting for flyovers...\n")

    client = OpenSkyClient(
        client_id=settings.opensky_client_id,
        client_secret=settings.opensky_client_secret,
        bbox=settings.bbox
    )

    seen: dict[str, float] = {}   # {icao24: last_seen_epoch}

    while True:
        try:
            vectors = client.fetch()
            now = time.time()
            for sv in vectors:
                if flyover_detector.is_flyover(sv, settings):
                    # Deduplicate: same plane can't trigger twice within 10 minutes (600s)
                    if now - seen.get(sv.icao24, 0) > 600:

                        # --- Attempt to get the true historical takeoff heading ---
                        # The live sv.true_track is the heading at this moment (mid-flight),
                        # which may differ significantly from the runway heading due to SID turns.
                        # The /tracks/all endpoint returns the full stored waypoint path;
                        # the first airborne waypoint is the closest approximation to liftoff.
                        track = client.get_track_by_aircraft(sv.icao24)
                        takeoff_hdg = runway_inferrer.extract_takeoff_heading(track)

                        if takeoff_hdg is not None:
                            # Use the historically-derived first-airborne heading
                            heading_for_runway = takeoff_hdg
                            heading_source = "historical_track"
                        else:
                            # Fall back to the current live heading if no track is available
                            # (e.g. unauthenticated, API outage, or no stored track yet)
                            heading_for_runway = sv.true_track
                            heading_source = "flyover_fallback"
                            print(f"[Track] No historical track for {sv.icao24} ({sv.callsign.strip()}); "
                                  "using live flyover heading as fallback.")

                        runway, label = runway_inferrer.infer_runway(heading_for_runway, settings.runways)
                        wind = weather_client.get_wind_kbwi()
                        enrichment = flight_enricher.enrich_flight(sv.icao24, sv.callsign)
                        record = record_builder.build(
                            sv, runway, label, wind, enrichment,
                            takeoff_heading_deg=takeoff_hdg,
                            heading_source=heading_source,
                        )
                        printer.print_and_log(record, velocity_mps=sv.velocity_mps)
                        seen[sv.icao24] = now
        except KeyboardInterrupt:
            print("\nExiting BWI Flyover Tracker. Goodbye!")
            break
        except Exception as e:
            print(f"[Error] Unexpected error in poll loop: {e}")

        time.sleep(settings.poll_interval_sec)

if __name__ == "__main__":
    main()
