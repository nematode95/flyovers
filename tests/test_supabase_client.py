import os
import unittest
from unittest.mock import Mock, patch

from supabase_client import upsert_live_snapshot


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

