import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class TestConsoleLogging(unittest.TestCase):
    def test_configure_logging_does_not_redirect_standard_streams(self):
        project_root = Path(__file__).resolve().parents[1]
        script = """
import sys

stdout = sys.stdout
stderr = sys.stderr
from api_logging import configure_logging

configure_logging()
print(f"stdout unchanged: {sys.stdout is stdout}")
print(f"stderr unchanged: {sys.stderr is stderr}", file=sys.stdout)
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

        self.assertIn("stdout unchanged: True", result.stdout)
        self.assertIn("stderr unchanged: True", result.stdout)


if __name__ == "__main__":
    unittest.main()
