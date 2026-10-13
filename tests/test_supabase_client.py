import os
import unittest
from unittest.mock import Mock, patch

from supabase_client import upsert_live_snapshot, upsert_recent_flyovers


class TestSupabaseClient(unittest.TestCase):
    def test_sync_is_disabled_when_credentials_are_absent(self):
        with patch.dict(os.environ, {"SUPABASE_URL": "", "SUPABASE_SERVICE_ROLE_KEY": ""}):
            with patch("supabase_client.requests.post") as mock_post:
                self.assertFalse(upsert_live_snapshot({"count": 0, "aircraft": []}))

        mock_post.assert_not_called()

    def test_partial_configuration_is_reported(self):
        with patch.dict(
            os.environ,
            {"SUPABASE_URL": "https://project.supabase.co", "SUPABASE_SERVICE_ROLE_KEY": ""},
        ):
            with self.assertRaisesRegex(RuntimeError, "Both SUPABASE_URL"):
                upsert_live_snapshot({"count": 0, "aircraft": []})

    def test_upserts_current_snapshot_using_service_credentials(self):
        response = Mock()
        response.status_code = 204
        response.text = ""
        response.raise_for_status.return_value = None
        payload = {
            "last_poll_time": "2026-10-11T07:00:00-04:00",
            "count": 1,
            "aircraft": [{"icao24": "abc123", "callsign": "SWA1"}],
        }

        with patch.dict(
            os.environ,
            {
                "SUPABASE_URL": "https://project.supabase.co/",
                "SUPABASE_SERVICE_ROLE_KEY": "service-role-secret",
            },
        ):
            with patch("supabase_client.requests.post", return_value=response) as mock_post:
                self.assertTrue(upsert_live_snapshot(payload))

        args, kwargs = mock_post.call_args
        self.assertEqual(args[0], "https://project.supabase.co/rest/v1/live_snapshot")
        self.assertEqual(kwargs["params"], {"on_conflict": "id"})
        self.assertEqual(kwargs["json"]["id"], "current")
        self.assertEqual(kwargs["json"]["payload"], payload)
        self.assertEqual(kwargs["headers"]["apikey"], "service-role-secret")
        self.assertEqual(
            kwargs["headers"]["Prefer"],
            "resolution=merge-duplicates,return=minimal",
        )
        response.raise_for_status.assert_called_once()

    def test_upserts_most_recent_flyovers_using_service_credentials(self):
        response = Mock()
        response.raise_for_status.return_value = None
        flyovers = [{"flight_number": f"SWA{number}"} for number in range(5, 0, -1)]

        with patch.dict(
            os.environ,
            {
                "SUPABASE_URL": "https://project.supabase.co/",
                "SUPABASE_SERVICE_ROLE_KEY": "service-role-secret",
            },
        ):
            with patch("supabase_client.requests.post", return_value=response) as mock_post:
                self.assertTrue(upsert_recent_flyovers(flyovers))

        args, kwargs = mock_post.call_args
        self.assertEqual(args[0], "https://project.supabase.co/rest/v1/recent_flyovers")
        self.assertEqual(kwargs["params"], {"on_conflict": "id"})
        self.assertEqual(kwargs["json"]["id"], "current")
        self.assertEqual(kwargs["json"]["flyovers"], flyovers)
        self.assertEqual(kwargs["headers"]["apikey"], "service-role-secret")
        response.raise_for_status.assert_called_once()

    def test_recent_flyover_sync_rejects_more_than_five_records(self):
        with self.assertRaisesRegex(ValueError, "At most five"):
            upsert_recent_flyovers([{}] * 6)

    def test_insert_runway_observation_batch_using_service_credentials(self):
        from supabase_client import insert_runway_observation_batch

        response = Mock()
        response.raise_for_status.return_value = None
        batch = {
            "id": "batch_20261013_120000",
            "count": 1,
            "reason": "batch_full",
            "observations": [{"flight_name": "SWA1"}],
        }

        with patch.dict(
            os.environ,
            {
                "SUPABASE_URL": "https://project.supabase.co/",
                "SUPABASE_SERVICE_ROLE_KEY": "service-role-secret",
            },
        ):
            with patch("supabase_client.requests.post", return_value=response) as mock_post:
                self.assertTrue(insert_runway_observation_batch(batch))

        args, kwargs = mock_post.call_args
        self.assertEqual(args[0], "https://project.supabase.co/rest/v1/runway_observations")
        self.assertEqual(kwargs["json"], batch)
        self.assertEqual(kwargs["headers"]["apikey"], "service-role-secret")
        self.assertEqual(kwargs["headers"]["Prefer"], "return=minimal")
        response.raise_for_status.assert_called_once()

