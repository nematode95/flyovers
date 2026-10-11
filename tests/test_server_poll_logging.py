import io
import os
import unittest
from contextlib import redirect_stdout
from unittest.mock import Mock, patch

from config import Settings
from opensky_client import StateVector
from server import FlyoverRequestHandler, TrackerWorker


class TestPollAircraftLogging(unittest.TestCase):
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

    def make_aircraft(self, altitude_m):
        return StateVector(
            icao24="000001",
            callsign="P01",
            longitude=-76.70,
            latitude=39.21,
            altitude_m=altitude_m,
            velocity_mps=100.0,
            true_track=0.0,
            on_ground=True,
            timestamp=0,
        )

    def test_logs_ten_closest_aircraft_first(self):
        worker = TrackerWorker(self.make_settings())
        worker.client = Mock()
        worker.client.fetch.return_value = [
            StateVector(
                icao24=f"{index:06x}",
                callsign=f"P{index:02}",
                longitude=-76.71 + index * 0.01,
                latitude=39.21,
                altitude_m=1000.0,
                velocity_mps=100.0,
                true_track=0.0,
                on_ground=True,
                timestamp=0,
            )
            for index in range(12, 0, -1)
        ]

        output = io.StringIO()
        with redirect_stdout(output):
            worker._poll_once()

        log = output.getvalue()
        self.assertLess(log.index("P01 ["), log.index("P02 ["))
        self.assertIn("P10 [", log)
        self.assertNotIn("P11 [", log)
        self.assertIn("+2 more", log)
        self.assertIn("P01 [000001]", log)
        self.assertIn("0.5nm", log)

    def test_colors_altitude_by_trend_and_high_altitude(self):
        worker = TrackerWorker(self.make_settings())
        worker.client = Mock()
        worker.client.fetch.side_effect = [
            [self.make_aircraft(1000.0)],
            [self.make_aircraft(1100.0)],
            [self.make_aircraft(900.0)],
            [self.make_aircraft(3100.0)],
        ]

        outputs = []
        for _ in range(4):
            output = io.StringIO()
            with redirect_stdout(output):
                worker._poll_once()
            outputs.append(output.getvalue())

        self.assertIn("\033[32m", outputs[1])
        self.assertIn("\033[32mP01\033[0m [000001]", outputs[1])
        self.assertIn("\033[31m", outputs[2])
        self.assertIn("\033[31mP01\033[0m [000001]", outputs[2])
        self.assertIn("\033[35m", outputs[3])
        self.assertIn("\033[35mP01\033[0m [000001]", outputs[3])

    def test_syncs_exact_live_snapshot_including_empty_polls(self):
        worker = TrackerWorker(self.make_settings())
        worker.current_vectors = [{"icao24": "stale"}]
        worker.client = Mock()
        worker.client.fetch.return_value = []

        with patch("server.supabase_client.upsert_live_snapshot") as sync_snapshot:
            worker._poll_once()

        snapshot = sync_snapshot.call_args.args[0]
        self.assertEqual(set(snapshot), {"last_poll_time", "count", "aircraft"})
        self.assertIsNotNone(snapshot["last_poll_time"])
        self.assertEqual(snapshot["count"], 0)
        self.assertEqual(snapshot["aircraft"], [])
        self.assertEqual(worker.get_live_snapshot(), snapshot)

    def test_supabase_failure_does_not_interrupt_poll(self):
        worker = TrackerWorker(self.make_settings())
        worker.client = Mock()
        worker.client.fetch.return_value = []

        with patch(
            "server.supabase_client.upsert_live_snapshot",
            side_effect=OSError("database unavailable"),
        ):
            worker._poll_once()

        self.assertEqual(worker.get_live_snapshot()["count"], 0)


class TestConfigEndpointAuth(unittest.TestCase):
    def make_handler(self, authorization=""):
        handler = object.__new__(FlyoverRequestHandler)
        handler.path = "/api/config"
        body = b'{"running": false}'
        handler.headers = {"Authorization": authorization, "Content-Length": str(len(body))}
        handler.rfile = io.BytesIO(body)
        handler.worker = Mock()
        handler._send_json = Mock()
        return handler

    def test_config_endpoint_is_disabled_without_token(self):
        handler = self.make_handler("Bearer valid-token")

        with patch.dict(os.environ, {"API_CONFIG_TOKEN": ""}):
            handler.do_POST()

        handler._send_json.assert_called_once_with(
            503,
            {"error": "Configuration endpoint is disabled; API_CONFIG_TOKEN is not set."},
        )
        handler.worker.set_config.assert_not_called()

    def test_config_endpoint_rejects_missing_or_invalid_token(self):
        for authorization in ("", "Bearer wrong-token", "Basic valid-token"):
            with self.subTest(authorization=authorization):
                handler = self.make_handler(authorization)

                with patch.dict(os.environ, {"API_CONFIG_TOKEN": "valid-token"}):
                    handler.do_POST()

                handler._send_json.assert_called_once_with(401, {"error": "Unauthorized"})
                handler.worker.set_config.assert_not_called()

    def test_config_endpoint_accepts_valid_bearer_token(self):
        handler = self.make_handler("Bearer valid-token")

        with patch.dict(os.environ, {"API_CONFIG_TOKEN": "valid-token"}):
            handler.do_POST()

        handler.worker.set_config.assert_called_once_with(running=False, poll_interval_sec=None)
        handler._send_json.assert_called_once_with(200, handler.worker.get_status())
