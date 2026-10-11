import logging
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from api_logging import MAX_RESPONSE_LOG_BYTES, _response_preview, logged_request


class TestApiLogging(unittest.TestCase):
    def test_configure_logging_captures_enabled_api_calls_with_existing_root_handler(self):
        project_root = Path(__file__).resolve().parents[1]
        script = """
import logging
import sys
from types import SimpleNamespace

logging.basicConfig(stream=sys.stderr, level=logging.INFO)

from api_logging import configure_logging, logged_request

configure_logging()
print("stdout remains connected")
logged_request(
    "Test API",
    "GET",
    "https://example.test/status",
    lambda url, **kwargs: SimpleNamespace(status_code=200, text='{"ok":true}'),
)
"""
        environment = os.environ.copy()
        environment["PYTHONPATH"] = str(project_root)
        environment["LOG_LEVEL"] = "INFO"
        environment["LOG_EXTERNAL_API"] = "true"

        with tempfile.TemporaryDirectory() as working_directory:
            result = subprocess.run(
                [sys.executable, "-c", script],
                cwd=working_directory,
                env=environment,
                check=True,
                capture_output=True,
                text=True,
            )

            log_contents = (Path(working_directory) / "flyovers.log").read_text(encoding="utf-8")

        self.assertIn("begin calling external API service=Test API", log_contents)
        self.assertIn("done calling external API service=Test API", log_contents)
        self.assertIn("stdout remains connected", result.stdout)

    def test_configure_logging_disables_external_api_calls_only(self):
        project_root = Path(__file__).resolve().parents[1]
        script = """
import logging
from types import SimpleNamespace

from api_logging import configure_logging, logged_request

configure_logging()
print("stdout remains connected")
logging.getLogger("urllib3.connectionpool").debug("Starting new HTTPS connection")
logged_request(
    "Test API",
    "GET",
    "https://example.test/status",
    lambda url, **kwargs: SimpleNamespace(status_code=200, text='{"ok":true}'),
)
"""
        environment = os.environ.copy()
        environment["PYTHONPATH"] = str(project_root)
        environment["LOG_EXTERNAL_API"] = "false"

        with tempfile.TemporaryDirectory() as working_directory:
            result = subprocess.run(
                [sys.executable, "-c", script],
                cwd=working_directory,
                env=environment,
                check=True,
                capture_output=True,
                text=True,
            )

            log_contents = (Path(working_directory) / "flyovers.log").read_text(encoding="utf-8")

        self.assertIn("stdout remains connected", result.stdout)
        self.assertNotIn("external API", log_contents)
        self.assertNotIn("Starting new HTTPS connection", result.stdout)
        self.assertNotIn("Starting new HTTPS connection", result.stderr)
        self.assertNotIn("Starting new HTTPS connection", log_contents)

    def test_response_preview_redacts_token_values(self):
        preview = _response_preview(
            '{"access_token":"private-token","supabase_service_role_key":"service-secret",'
            '"expires_in":60}'
        )

        self.assertIn('"access_token": "[REDACTED]"', preview)
        self.assertNotIn("private-token", preview)
        self.assertNotIn("service-secret", preview)

    def test_response_preview_caps_large_bodies(self):
        preview = _response_preview("x" * (MAX_RESPONSE_LOG_BYTES + 100))

        self.assertIn("[truncated at 1024 bytes]", preview)
        self.assertLessEqual(len(preview.split("…", 1)[0].encode("utf-8")), MAX_RESPONSE_LOG_BYTES)

    def test_logged_request_logs_begin_and_http_response_without_query(self):
        requester = Mock(return_value=SimpleNamespace(status_code=200, text='{"states":[]}'))

        with self.assertLogs("external_api", level=logging.DEBUG) as captured:
            response = logged_request(
                "OpenSky states",
                "GET",
                "https://opensky-network.org/api/states/all",
                requester,
                params={"icao24": "abc123"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertIn("begin calling external API", captured.output[0])
        self.assertIn("done calling external API", captured.output[1])
        self.assertIn("http_code=200", captured.output[1])
        self.assertIn('response={"states": []}', captured.output[1])
        self.assertNotIn("abc123", "\n".join(captured.output))

    def test_logged_request_logs_network_error_and_reraises(self):
        requester = Mock(
            side_effect=TimeoutError(
                "request timed out for url: /search?q=private+home+address&format=json"
            )
        )

        with self.assertLogs("external_api", level=logging.DEBUG) as captured:
            with self.assertRaises(TimeoutError):
                logged_request("NOAA", "GET", "https://example.test/data", requester)

        self.assertIn("begin calling external API", captured.output[0])
        self.assertIn("done calling external API", captured.output[1])
        self.assertIn("request timed out", captured.output[1])
        self.assertNotIn("private+home+address", captured.output[1])
