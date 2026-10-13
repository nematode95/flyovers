import collections
from datetime import datetime, timezone
import json
import logging
import os
import threading
import time
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, urlparse

from config import Settings
from opensky_client import StateVector
from record_builder import FlyoverRecord
import server
import supabase_client

logger = logging.getLogger(__name__)


def flyover_record_to_observation(record: FlyoverRecord) -> dict[str, Any]:
    """Maps a FlyoverRecord dataclass to the observation JSON schema."""
    return {
        "takeoff_runway": record.runway,
        "runway_explanation": record.runway_explanation,
        "wind_speed_kt": record.wind_speed_kt,
        "wind_direction_deg": record.wind_direction_deg,
        "flight_name": record.flight_number,
        "icao24": record.icao24,
        "flight_dest": record.destination,
        "takeoff_heading": record.takeoff_heading_deg,
        "flyover_heading": record.flyover_track_deg,
        "flyover_altitude": record.altitude_ft,
        "timestamp": record.timestamp,
    }


class RunwayObserverWorker(server.TrackerWorker):
    def __init__(
        self,
        settings: Settings,
        batch_size: int = 5,
        hiatus_min: float = 30.0,
        timeout_min: float = 30.0,
        log_file: str = "flyovers.jsonl",
    ):
        super().__init__(settings=settings, log_file=log_file)
        self.batch_size: int = max(1, batch_size)
        self.hiatus_sec: float = max(0.0, hiatus_min * 60.0)
        self.timeout_sec: float = max(0.0, timeout_min * 60.0)

        # State machine
        self.state: str = "POLLING"  # "POLLING" | "HIATUS"
        self.current_batch: List[dict[str, Any]] = []
        self.recent_bundles: collections.deque[dict[str, Any]] = collections.deque(maxlen=5)

        self.polling_started_at: float = time.time()
        self.last_flyover_at: Optional[float] = None
        self.hiatus_until: Optional[float] = None
        self.last_bundle_reason: Optional[str] = None

    def _on_flyover_detected(self, record: FlyoverRecord, sv: StateVector, detected_epoch: float):
        # Still log to JSONL file and mark seen
        super()._on_flyover_detected(record, sv, detected_epoch)

        obs = flyover_record_to_observation(record)
        with self._lock:
            self.current_batch.append(obs)
            self.last_flyover_at = detected_epoch
            time_str = datetime.now().strftime("%H:%M:%S")
            print(
                f"[{time_str}] [RunwayObserver] Collected observation {len(self.current_batch)}/{self.batch_size} "
                f"for flight {record.flight_number} (Runway: {record.runway})"
            )
            if len(self.current_batch) >= self.batch_size:
                self._flush_batch_and_enter_hiatus(reason="batch_full")

    def _flush_batch_and_enter_hiatus(self, reason: str):
        """Flushes the current batch to Supabase (if any items) and transitions to HIATUS."""
        time_str = datetime.now().strftime("%H:%M:%S")
        if self.current_batch:
            now_utc = datetime.now(timezone.utc)
            batch_id = f"batch_{now_utc.strftime('%Y%m%d_%H%M%S')}"
            bundle = {
                "id": batch_id,
                "created_at": now_utc.isoformat(timespec="seconds"),
                "count": len(self.current_batch),
                "reason": reason,
                "observations": list(self.current_batch),
            }
            try:
                supabase_client.insert_runway_observation_batch(bundle)
                print(f"[{time_str}] [RunwayObserver] Batch of {len(self.current_batch)} observations sent to Supabase.")
            except Exception as e:
                logger.error("Failed to insert runway observation batch to Supabase: %s", e)
                print(f"[{time_str}] [RunwayObserver] Failed to send batch to Supabase: {e}")

            self.recent_bundles.append(bundle)
            self.current_batch.clear()
        else:
            print(f"[{time_str}] [RunwayObserver] No observations to flush ({reason}).")

        self.state = "HIATUS"
        self.hiatus_until = time.time() + self.hiatus_sec
        self.last_bundle_reason = reason
        print(f"[{time_str}] [RunwayObserver] Entering HIATUS for {self.hiatus_sec / 60:.1f} minutes.")

    def get_status(self) -> Dict[str, Any]:
        with self._lock:
            status = super().get_status()
            now = time.time()
            hiatus_remaining_sec = max(0, int(self.hiatus_until - now)) if self.hiatus_until else 0
            time_in_polling_sec = max(0, int(now - self.polling_started_at)) if self.state == "POLLING" else 0
            status.update({
                "observer_state": self.state,
                "batch_size": self.batch_size,
                "current_batch_count": len(self.current_batch),
                "hiatus_duration_min": round(self.hiatus_sec / 60.0, 1),
                "hiatus_remaining_sec": hiatus_remaining_sec,
                "timeout_duration_min": round(self.timeout_sec / 60.0, 1),
                "time_in_polling_sec": time_in_polling_sec,
                "total_bundles_sent": len(self.recent_bundles),
                "last_bundle_reason": self.last_bundle_reason,
            })
            return status

    def get_runway_bundles(self) -> List[Dict[str, Any]]:
        with self._lock:
            # Return newest bundles first
            return list(reversed(self.recent_bundles))

    def _run_loop(self):
        print(
            f"[RunwayObserver] Worker started. Batch size: {self.batch_size}, "
            f"Hiatus: {self.hiatus_sec / 60:.1f}m, Timeout: {self.timeout_sec / 60:.1f}m."
        )
        was_paused = False
        while not self._stop_event.is_set():
            now = time.time()

            # Handle HIATUS state
            if self.state == "HIATUS":
                if self.hiatus_until is not None and now >= self.hiatus_until:
                    with self._lock:
                        time_str = datetime.now().strftime("%H:%M:%S")
                        print(f"[{time_str}] [RunwayObserver] Hiatus expired. Resuming POLLING.")
                        self.state = "POLLING"
                        self.hiatus_until = None
                        self.polling_started_at = now
                        self.last_flyover_at = None
                else:
                    # Sleep briefly and recheck stop event
                    time.sleep(1)
                    continue

            # Handle POLLING state
            if not self.running:
                if not was_paused:
                    time_str = datetime.now().strftime("%H:%M:%S")
                    print(f"[{time_str}] [Worker] Polling is PAUSED. Standing by...")
                    was_paused = True
                time.sleep(1)
                continue

            was_paused = False

            # Check timeout condition
            reference_time = self.last_flyover_at if self.last_flyover_at is not None else self.polling_started_at
            if (now - reference_time) >= self.timeout_sec:
                with self._lock:
                    time_str = datetime.now().strftime("%H:%M:%S")
                    print(
                        f"[{time_str}] [RunwayObserver] Polling timeout reached ({self.timeout_sec / 60:.1f}m without flyover)."
                    )
                    self._flush_batch_and_enter_hiatus(reason="inactivity_timeout")
                continue

            # Poll OpenSky
            try:
                self._poll_once()
                with self._lock:
                    self.last_error = None
            except Exception as e:
                with self._lock:
                    self.last_error = str(e)
                time_str = datetime.now().strftime("%H:%M:%S")
                print(f"[{time_str}] [Poll Error] {e}")

            # Sleep poll_interval_sec responsive to stop event
            start_wait = time.time()
            interval = self.poll_interval_sec
            while (time.time() - start_wait) < interval:
                if self._stop_event.is_set():
                    return
                time.sleep(0.5)
                interval = self.poll_interval_sec


class RunwayObserverRequestHandler(server.FlyoverRequestHandler):
    worker: RunwayObserverWorker

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")
        query = parse_qs(parsed.query)
        print(f"[HTTP] GET {path} with query {query}")

        if path in ("/api/status", ""):
            self._send_json(200, self.worker.get_status())
            return
        elif path == "/api/runways":
            self._send_json(200, self.worker.get_runway_bundles())
            return
        elif path == "/api/live":
            self._send_json(200, self.worker.get_live_snapshot())
            return
        elif path == "/api/flyovers":
            # Delegate to existing log_file reader in base class
            super().do_GET()
            return
        else:
            self._send_json(
                404,
                {
                    "error": "Not Found",
                    "available_endpoints": ["/api/runways", "/api/status", "/api/live", "/api/flyovers", "/api/config"],
                },
            )
