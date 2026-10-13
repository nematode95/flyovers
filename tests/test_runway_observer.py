import os
import unittest
from unittest.mock import Mock, patch

from record_builder import FlyoverRecord
from runway_observer import RunwayObserverWorker, RunwayObserverRequestHandler, flyover_record_to_observation
from config import Settings
from opensky_client import StateVector


class TestRunwayObserver(unittest.TestCase):
    def setUp(self):
        self.supabase_env = patch.dict(
            os.environ,
            {"SUPABASE_URL": "", "SUPABASE_SERVICE_ROLE_KEY": ""},
        )
        self.supabase_env.start()
        self.addCleanup(self.supabase_env.stop)

    def make_settings(self):
        return Settings(
            opensky_client_id="",
            opensky_client_secret="",
            listen_address="test address",
            listen_lat=39.21,
            listen_lon=-76.71,
            flyover_radius_nm=1.0,
            bbox_padding_nm=20.0,
            bbox={},
            poll_interval_sec=30,
        )

    def make_record(self, flight_number="SWA123", runway="28"):
        return FlyoverRecord(
            timestamp="2026-10-13T12:00:00-04:00",
            flight_number=flight_number,
            icao24="a1b2c3",
            aircraft_type="B738",
            aircraft_model="Boeing 737-800",
            destination="FLL",
            route="BWI ⟶ FLL",
            altitude_ft=2400,
            flyover_track_deg=285.0,
            takeoff_heading_deg=283.0,
            heading_source="historical_track",
            runway=runway,
            runway_direction="28 (West)",
            wind_direction_deg=310,
            wind_speed_kt=8,
            wind_gust_kt=None,
            raw_metar="METAR KBWI ...",
            runway_explanation="Heading 283° closely matches runway 28 (285°)",
        )

    def make_state_vector(self, icao24="a1b2c3", callsign="SWA123"):
        return StateVector(
            icao24=icao24,
            callsign=callsign,
            longitude=-76.71,
            latitude=39.21,
            altitude_m=730.0,
            velocity_mps=120.0,
            true_track=285.0,
            on_ground=False,
            timestamp=1234567,
        )

    def test_flyover_record_to_observation_mapping(self):
        record = self.make_record()
        obs = flyover_record_to_observation(record)

        self.assertEqual(obs["takeoff_runway"], "28")
        self.assertEqual(obs["runway_explanation"], "Heading 283° closely matches runway 28 (285°)")
        self.assertEqual(obs["wind_speed_kt"], 8)
        self.assertEqual(obs["wind_direction_deg"], 310)
        self.assertEqual(obs["flight_name"], "SWA123")
        self.assertEqual(obs["icao24"], "a1b2c3")
        self.assertEqual(obs["flight_dest"], "FLL")
        self.assertEqual(obs["takeoff_heading"], 283.0)
        self.assertEqual(obs["flyover_heading"], 285.0)
        self.assertEqual(obs["flyover_altitude"], 2400)
        self.assertEqual(obs["timestamp"], "2026-10-13T12:00:00-04:00")

    def test_batches_observations_and_enters_hiatus_when_full(self):
        worker = RunwayObserverWorker(
            settings=self.make_settings(),
            batch_size=3,
            hiatus_min=10.0,
            timeout_min=15.0,
            log_file="/tmp/test_flyovers.jsonl",
        )

        with patch("runway_observer.supabase_client.insert_runway_observation_batch") as mock_supabase:
            mock_supabase.return_value = True

            # Add 2 observations -> state remains POLLING
            worker._on_flyover_detected(self.make_record("SWA1"), self.make_state_vector("000001", "SWA1"), 100.0)
            worker._on_flyover_detected(self.make_record("SWA2"), self.make_state_vector("000002", "SWA2"), 110.0)

            self.assertEqual(worker.state, "POLLING")
            self.assertEqual(len(worker.current_batch), 2)
            mock_supabase.assert_not_called()

            # Add 3rd observation -> triggers batch flush and hiatus
            worker._on_flyover_detected(self.make_record("SWA3"), self.make_state_vector("000003", "SWA3"), 120.0)

            self.assertEqual(worker.state, "HIATUS")
            self.assertEqual(len(worker.current_batch), 0)
            self.assertEqual(len(worker.recent_bundles), 1)

            mock_supabase.assert_called_once()
            bundle = mock_supabase.call_args[0][0]
            self.assertEqual(bundle["count"], 3)
            self.assertEqual(bundle["reason"], "batch_full")
            self.assertEqual(len(bundle["observations"]), 3)
            self.assertEqual(bundle["observations"][0]["flight_name"], "SWA1")
            self.assertEqual(bundle["observations"][2]["flight_name"], "SWA3")

    def test_inactivity_timeout_flushes_partial_batch_and_enters_hiatus(self):
        worker = RunwayObserverWorker(
            settings=self.make_settings(),
            batch_size=5,
            hiatus_min=10.0,
            timeout_min=15.0,
            log_file="/tmp/test_flyovers.jsonl",
        )

        with patch("runway_observer.supabase_client.insert_runway_observation_batch") as mock_supabase:
            mock_supabase.return_value = True

            # Record 1 flyover
            worker._on_flyover_detected(self.make_record("SWA1"), self.make_state_vector("000001", "SWA1"), 100.0)
            self.assertEqual(len(worker.current_batch), 1)

            # Trigger timeout flush
            worker._flush_batch_and_enter_hiatus(reason="inactivity_timeout")

            self.assertEqual(worker.state, "HIATUS")
            self.assertEqual(len(worker.current_batch), 0)
            self.assertEqual(len(worker.recent_bundles), 1)

            mock_supabase.assert_called_once()
            bundle = mock_supabase.call_args[0][0]
            self.assertEqual(bundle["count"], 1)
            self.assertEqual(bundle["reason"], "inactivity_timeout")

    def test_empty_batch_timeout_does_not_call_supabase(self):
        worker = RunwayObserverWorker(
            settings=self.make_settings(),
            batch_size=5,
            hiatus_min=10.0,
            timeout_min=15.0,
            log_file="/tmp/test_flyovers.jsonl",
        )

        with patch("runway_observer.supabase_client.insert_runway_observation_batch") as mock_supabase:
            worker._flush_batch_and_enter_hiatus(reason="inactivity_timeout")

            self.assertEqual(worker.state, "HIATUS")
            self.assertEqual(len(worker.recent_bundles), 0)
            mock_supabase.assert_not_called()

    def test_recent_bundles_keeps_at_most_five(self):
        worker = RunwayObserverWorker(
            settings=self.make_settings(),
            batch_size=1,
            hiatus_min=1.0,
            timeout_min=1.0,
            log_file="/tmp/test_flyovers.jsonl",
        )

        with patch("runway_observer.supabase_client.insert_runway_observation_batch", return_value=True):
            for i in range(7):
                worker.state = "POLLING"
                worker._on_flyover_detected(
                    self.make_record(f"SWA{i}"),
                    self.make_state_vector(f"00000{i}", f"SWA{i}"),
                    float(100 + i),
                )

        bundles = worker.get_runway_bundles()
        self.assertEqual(len(bundles), 5)
        # Newest first
        self.assertEqual(bundles[0]["observations"][0]["flight_name"], "SWA6")
        self.assertEqual(bundles[4]["observations"][0]["flight_name"], "SWA2")

    def test_status_endpoint_data(self):
        worker = RunwayObserverWorker(
            settings=self.make_settings(),
            batch_size=5,
            hiatus_min=30.0,
            timeout_min=30.0,
            log_file="/tmp/test_flyovers.jsonl",
        )

        status = worker.get_status()
        self.assertIn("observer_state", status)
        self.assertEqual(status["observer_state"], "POLLING")
        self.assertEqual(status["batch_size"], 5)
        self.assertEqual(status["current_batch_count"], 0)
        self.assertEqual(status["hiatus_duration_min"], 30.0)
        self.assertEqual(status["timeout_duration_min"], 30.0)


if __name__ == "__main__":
    unittest.main()
