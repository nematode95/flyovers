import hmac
import json
import logging
import os
import threading
import time
from datetime import datetime
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from typing import Optional, List, Dict, Any

from api_logging import configure_logging
from config import load_settings, Settings
from opensky_client import OpenSkyClient, StateVector
import flyover_detector
import runway_inferrer
import weather_client
import flight_enricher
import record_builder
import printer
import supabase_client


logger = logging.getLogger(__name__)


class TrackerWorker:
    def __init__(self, settings: Settings, log_file: str = "flyovers.jsonl"):
        self.settings = settings
        self.log_file = os.path.abspath(log_file)
        self.client = OpenSkyClient(
            client_id=settings.opensky_client_id,
            client_secret=settings.opensky_client_secret,
            bbox=settings.bbox,
        )
        self.seen: Dict[str, float] = {}  # {icao24: last_seen_epoch}
        self.previous_altitudes_m: Dict[str, float] = {}
        self.running: bool = True
        self.poll_interval_sec: int = settings.poll_interval_sec
        self.last_poll_time: Optional[str] = None
        self.last_poll_aircraft_count: int = 0
        self.last_error: Optional[str] = None
        self.current_vectors: List[Dict[str, Any]] = []
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self):
        self._thread = threading.Thread(target=self._run_loop, name="TrackerWorker", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)

    def set_config(self, running: Optional[bool] = None, poll_interval_sec: Optional[int] = None):
        with self._lock:
            time_str = datetime.now().strftime("%H:%M:%S")
            if running is not None:
                old_running = self.running
                self.running = bool(running)
                if old_running != self.running:
                    state_str = "RESUMED" if self.running else "PAUSED"
                    print(f"[{time_str}] [Worker] Polling {state_str} via API.")
            if poll_interval_sec is not None and poll_interval_sec >= 5:
                self.poll_interval_sec = int(poll_interval_sec)
                print(f"[{time_str}] [Worker] Poll interval updated to {self.poll_interval_sec}s.")

    def count_logged_flyovers(self) -> int:
        if not os.path.exists(self.log_file):
            return 0
        try:
            with open(self.log_file, "r", encoding="utf-8") as f:
                return sum(1 for line in f if line.strip())
        except Exception:
            return 0

    def get_status(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "running": self.running,
                "poll_interval_sec": self.poll_interval_sec,
                "last_poll_time": self.last_poll_time,
                "last_poll_aircraft_count": self.last_poll_aircraft_count,
                "last_error": self.last_error,
                "total_logged": self.count_logged_flyovers(),
                "listen_address": self.settings.listen_address,
                "listen_lat": self.settings.listen_lat,
                "listen_lon": self.settings.listen_lon,
                "flyover_radius_nm": self.settings.flyover_radius_nm,
            }

    def get_live_snapshot(self) -> Dict[str, Any]:
        with self._lock:
            aircraft = [dict(vector) for vector in self.current_vectors]
            return {
                "last_poll_time": self.last_poll_time,
                "count": len(aircraft),
                "aircraft": aircraft,
            }

    def _bbox_altitude_color(self, sv: StateVector) -> str:
        altitude_ft = int(round(sv.altitude_m * 3.28084))
        previous_altitude_m = self.previous_altitudes_m.get(sv.icao24)

        if altitude_ft > flyover_detector.MAX_FLYOVER_ALTITUDE_FT:
            return "\033[35m"
        if previous_altitude_m is not None and sv.altitude_m > previous_altitude_m:
            return "\033[32m"
        if previous_altitude_m is not None and sv.altitude_m < previous_altitude_m:
            return "\033[31m"
        return ""

    def _poll_once(self):
               
        vectors = self.client.fetch()
        now = time.time()
        time_str = datetime.now().strftime("%H:%M:%S")
        local_now = datetime.now().astimezone().isoformat(timespec="seconds")

        with self._lock:
            self.last_poll_time = local_now
            self.last_poll_aircraft_count = len(vectors)
            self.current_vectors = [
                {
                    "icao24": sv.icao24,
                    "callsign": sv.callsign.strip(),
                    "lat": sv.latitude,
                    "lon": sv.longitude,
                    "altitude_m": sv.altitude_m,
                    "altitude_ft": int(round(sv.altitude_m * 3.28084)),
                    "velocity_mps": sv.velocity_mps,
                    "true_track": sv.true_track,
                }
                for sv in vectors
            ]

        try:
            supabase_client.upsert_live_snapshot(self.get_live_snapshot())
        except Exception as error:
            logger.error("Failed to sync live snapshot to Supabase: %s", error)

        # Check for flyovers
        flyovers_to_process = []
        for sv in vectors:
            if flyover_detector.is_flyover(sv, self.settings):
                elapsed = now - self.seen.get(sv.icao24, 0)
                if elapsed > 600:
                    flyovers_to_process.append(sv)
                else:
                    cs = sv.callsign.strip() or sv.icao24
                    print(f"[{time_str}] [Dedupe] {cs} detected in zone, but already logged {int(elapsed)}s ago; skipping.")

        # Log poll summary
        if not vectors:
            print(f"[{time_str}] [Poll] 0 aircraft in bounding box.")
        else:
            aircraft_by_distance = sorted(
                [
                    (
                        sv,
                        flyover_detector.haversine_nm(
                            sv.latitude,
                            sv.longitude,
                            self.settings.listen_lat,
                            self.settings.listen_lon,
                        ),
                    )
                    for sv in vectors
                ],
                key=lambda item: item[1],
            )
            ac_list = []
            for sv, distance_nm in aircraft_by_distance[:10]:
                cs = sv.callsign.strip() or sv.icao24
                color = self._bbox_altitude_color(sv)
                alt = f"{int(round(sv.altitude_m * 3.28084)):,}ft"
                if color:
                    cs = f"{color}{cs}\033[0m"
                    alt = f"{color}{alt}\033[0m"
                ac_list.append(f"{cs} [{sv.icao24}] ({alt}, {distance_nm:.1f}nm)")
            extra = f" +{len(vectors) - 10} more" if len(vectors) > 10 else ""
            flyover_summary = (
                f" — ✈ {len(flyovers_to_process)} NEW FLYOVER DETECTED!"
                if flyovers_to_process
                else " — 0 flyovers."
            )
           
            print(
                f"[{time_str}] [Poll] {len(vectors)} aircraft in bbox "
                f"[{', '.join(ac_list)}{extra}]{flyover_summary}"
            )

        self.previous_altitudes_m = {sv.icao24: sv.altitude_m for sv in vectors}

        for sv in flyovers_to_process:
            track = self.client.get_track_by_aircraft(sv.icao24)
            takeoff_hdg = runway_inferrer.extract_takeoff_heading(track)

            if takeoff_hdg is not None:
                heading_for_runway = takeoff_hdg
                heading_source = "historical_track"
            else:
                heading_for_runway = sv.true_track
                heading_source = "flyover_fallback"
                print(
                    f"[{time_str}] [Track] No historical track for {sv.icao24} ({sv.callsign.strip()}); "
                    "using live flyover heading as fallback."
                )

            runway, label = runway_inferrer.infer_runway(heading_for_runway, self.settings.runways)
            wind = weather_client.get_wind_kbwi()
            enrichment = flight_enricher.enrich_flight(sv.icao24, sv.callsign)
            record = record_builder.build(
                sv,
                runway,
                label,
                wind,
                enrichment,
                takeoff_heading_deg=takeoff_hdg,
                heading_source=heading_source,
            )
            printer.print_and_log(record, velocity_mps=sv.velocity_mps, log_file=self.log_file)
            self.seen[sv.icao24] = now

    def _run_loop(self):
        print(f"[Worker] Tracker background thread started. Polling every {self.poll_interval_sec}s.")
        was_paused = False
        while not self._stop_event.is_set():
            if self.running:
                was_paused = False
                try:
                    self._poll_once()
                    with self._lock:
                        self.last_error = None
                except Exception as e:
                    with self._lock:
                        self.last_error = str(e)
                    time_str = datetime.now().strftime("%H:%M:%S")
                    print(f"[{time_str}] [Poll Error] {e}")
            else:
                if not was_paused:
                    time_str = datetime.now().strftime("%H:%M:%S")
                    print(f"[{time_str}] [Worker] Polling is PAUSED. Standing by...")
                    was_paused = True

            # Wait poll_interval_sec or respond quickly if stopped/paused
            start_wait = time.time()
            interval = self.poll_interval_sec
            while (time.time() - start_wait) < interval:
                if self._stop_event.is_set():
                    return
                time.sleep(0.5)
                interval = self.poll_interval_sec


class FlyoverRequestHandler(BaseHTTPRequestHandler):
    worker: TrackerWorker
    log_file: str = os.path.abspath("flyovers.jsonl")

    def _send_cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")

    def _send_json(self, status_code: int, data: Any):
        body = json.dumps(data, indent=2).encode("utf-8")
       
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Connection", "close")
        self._send_cors_headers()
        self.end_headers()
        self.wfile.write(body)
    
    def do_OPTIONS(self):
        self.send_response(204)
        self._send_cors_headers()
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")
        query = parse_qs(parsed.query)
        print(f"[HTTP] GET {path} with query {query}")
        if path == "/api/status" or path == "":
            self._send_json(200, self.worker.get_status())
            return

        elif path == "/api/flyovers":
            limit = 50
            if "limit" in query:
                try:
                    limit = max(1, int(query["limit"][0]))
                except ValueError:
                    pass

            records = []
            if os.path.exists(self.log_file):
                try:
                    with open(self.log_file, "r", encoding="utf-8") as f:
                        for line in f:
                            line = line.strip()
                            if line:
                                try:
                                    records.append(json.loads(line))
                                except json.JSONDecodeError:
                                    continue
                except Exception as e:
                    self._send_json(500, {"error": f"Failed to read log file: {e}"})
                    return

            # Return newest records first
            records.reverse()
            self._send_json(200, records[:limit])
            return

        elif path == "/api/live":
            self._send_json(200, self.worker.get_live_snapshot())
            return

        else:
            self._send_json(404, {"error": "Not Found", "available_endpoints": ["/api/flyovers", "/api/status", "/api/live", "/api/config"]})

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")

        if path == "/api/config":
            config_token = os.getenv("API_CONFIG_TOKEN", "")
            if not config_token:
                self._send_json(503, {"error": "Configuration endpoint is disabled; API_CONFIG_TOKEN is not set."})
                return

            authorization = self.headers.get("Authorization", "")
            scheme, separator, supplied_token = authorization.partition(" ")
            if (
                scheme.lower() != "bearer"
                or not separator
                or not hmac.compare_digest(supplied_token, config_token)
            ):
                self._send_json(401, {"error": "Unauthorized"})
                return

            try:
                content_len = int(self.headers.get("Content-Length", 0))
                raw_body = self.rfile.read(content_len).decode("utf-8")
                payload = json.loads(raw_body) if raw_body else {}
            except Exception as e:
                self._send_json(400, {"error": f"Invalid JSON payload: {e}"})
                return

            running = payload.get("running")
            poll_interval = payload.get("poll_interval_sec")

            if running is not None or poll_interval is not None:
                self.worker.set_config(running=running, poll_interval_sec=poll_interval)
                print(f"[Config Updated] running={self.worker.running}, poll_interval_sec={self.worker.poll_interval_sec}")

            self._send_json(200, self.worker.get_status())
            return

        else:
            self._send_json(404, {"error": "Not Found"})

    def log_message(self, format, *args):
        # Concise logging format for HTTP requests
        print(f"[HTTP] {self.address_string()} - {format % args}")


def run_server(port: int = 8080):
    configure_logging()
    settings = load_settings()
    log_file = "flyovers.jsonl"

    worker = TrackerWorker(settings=settings, log_file=log_file)
    worker.start()

    FlyoverRequestHandler.worker = worker
    FlyoverRequestHandler.log_file = log_file

    server_address = ("0.0.0.0", port)
    ThreadingHTTPServer.allow_reuse_address = True
    httpd = ThreadingHTTPServer(server_address, FlyoverRequestHandler)

    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(f"✈  Flyover JSON Server is running!")
    print(f"📡  Listening on       : http://0.0.0.0:{port}")
    print(f"📄  Flyovers endpoint  : http://localhost:{port}/api/flyovers")
    print(f"⚙   Status endpoint    : http://localhost:{port}/api/status")
    print(f"✈   Live bbox aircraft : http://localhost:{port}/api/live")
    print(f"🛑  Config/Toggle      : POST http://localhost:{port}/api/config")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down server...")
    finally:
        worker.stop()
        httpd.server_close()
        print("Server stopped cleanly.")


if __name__ == "__main__":
    port_env = int(os.getenv("PORT", "8080"))
    run_server(port=port_env)
