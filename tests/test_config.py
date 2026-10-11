import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from config import compute_bbox, load_settings, write_bbox_map


class TestComputeBbox(unittest.TestCase):
    def test_bbox_is_centered_on_listening_location(self):
        bbox = compute_bbox(39.21, -76.71, radius_nm=1.0, padding_nm=20.0)

        self.assertAlmostEqual((bbox["lamin"] + bbox["lamax"]) / 2, 39.21, places=4)
        self.assertAlmostEqual((bbox["lomin"] + bbox["lomax"]) / 2, -76.71, places=4)

    def test_padding_widens_bbox_without_changing_center(self):
        small = compute_bbox(39.21, -76.71, radius_nm=1.0, padding_nm=5.0)
        large = compute_bbox(39.21, -76.71, radius_nm=1.0, padding_nm=20.0)

        self.assertLess(large["lamin"], small["lamin"])
        self.assertGreater(large["lamax"], small["lamax"])
        self.assertLess(large["lomin"], small["lomin"])
        self.assertGreater(large["lomax"], small["lomax"])

    def test_write_bbox_map_saves_interactive_map_and_logs_link(self):
        bbox = compute_bbox(39.21, -76.71, radius_nm=1.0, padding_nm=20.0)
        with tempfile.TemporaryDirectory() as directory:
            map_path = Path(directory) / "bbox_map.html"
            with patch("config.Path.cwd", return_value=Path(directory)):
                with self.assertLogs("config", level="INFO") as captured:
                    result = write_bbox_map(39.21, -76.71, bbox)

            html = map_path.read_text(encoding="utf-8")
            self.assertTrue(map_path.is_file())

        self.assertEqual(result, map_path)
        self.assertIn("<html", html)
        self.assertIn("OpenSky BBox", html)
        self.assertIn("OpenSky bounding-box map:", captured.output[0])
        self.assertIn(map_path.as_uri(), captured.output[0])

    @patch("config.geocode_address", return_value=(39.21, -76.71))
    def test_padding_is_configurable_from_environment(self, _geocode):
        env = {
            "LISTEN_ADDRESS": "test address",
            "FLYOVER_RADIUS_NM": "1.0",
            "BBOX_PADDING_NM": "10.0",
            "POLL_INTERVAL_SEC": "30",
        }
        with tempfile.TemporaryDirectory() as directory:
            with patch("config.Path.cwd", return_value=Path(directory)):
                with patch.dict(os.environ, env):
                    settings = load_settings()
            self.assertTrue((Path(directory) / "bbox_map.html").is_file())

        self.assertEqual(settings.bbox_padding_nm, 10.0)
        self.assertAlmostEqual(
            (settings.bbox["lamax"] - settings.bbox["lamin"]) * 60 / 2,
            11.0,
            places=2,
        )
