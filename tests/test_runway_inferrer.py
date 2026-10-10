import unittest
import runway_inferrer
from opensky_client import TrackWaypoint

class TestRunwayInferrer(unittest.TestCase):
    def setUp(self):
        self.runways = {"10": 105, "28": 285, "15R": 155, "33L": 335}

    def test_runway_28_exact(self):
        rwy_id, label = runway_inferrer.infer_runway(285.0, self.runways)
        self.assertEqual(rwy_id, "28")
        self.assertIn("28", label)

    def test_runway_28_within_tolerance(self):
        rwy_id, label = runway_inferrer.infer_runway(281.4, self.runways)
        self.assertEqual(rwy_id, "28")
        self.assertIn("28", label)

    def test_runway_33L(self):
        rwy_id, label = runway_inferrer.infer_runway(335.0, self.runways)
        self.assertEqual(rwy_id, "33L")
        self.assertIn("33L", label)

    def test_runway_10(self):
        rwy_id, label = runway_inferrer.infer_runway(108.0, self.runways)
        self.assertEqual(rwy_id, "10")
        self.assertIn("10", label)

    def test_unknown_runway_outside_tolerance(self):
        # Heading 50° is not close to any runway (min diff ~55°)
        rwy_id, label = runway_inferrer.infer_runway(50.0, self.runways)
        self.assertEqual(rwy_id, "UNKNOWN")
        self.assertEqual(label, "Unknown direction")

    def test_invalid_track(self):
        rwy_id, label = runway_inferrer.infer_runway(None, self.runways)
        self.assertEqual(rwy_id, "UNKNOWN")


def _wp(on_ground: bool, true_track, timestamp: int = 0) -> TrackWaypoint:
    """Helper to build a minimal TrackWaypoint."""
    return TrackWaypoint(
        timestamp=timestamp,
        latitude=39.175,
        longitude=-76.668,
        altitude_m=0.0 if on_ground else 300.0,
        true_track=true_track,
        on_ground=on_ground,
    )


class TestExtractTakeoffHeading(unittest.TestCase):
    def test_returns_first_airborne_heading(self):
        """Should skip ground waypoints and return the heading of the first airborne one."""
        track = [
            _wp(on_ground=True,  true_track=285.0, timestamp=1),
            _wp(on_ground=True,  true_track=285.0, timestamp=2),
            _wp(on_ground=False, true_track=283.0, timestamp=3),  # liftoff
            _wp(on_ground=False, true_track=260.0, timestamp=4),  # post-SID turn
        ]
        result = runway_inferrer.extract_takeoff_heading(track)
        self.assertAlmostEqual(result, 283.0)

    def test_skips_none_heading_at_liftoff(self):
        """If the first airborne waypoint has true_track=None, it should continue to the next."""
        track = [
            _wp(on_ground=True,  true_track=285.0, timestamp=1),
            _wp(on_ground=False, true_track=None,  timestamp=2),  # no heading data yet
            _wp(on_ground=False, true_track=287.0, timestamp=3),  # valid
        ]
        result = runway_inferrer.extract_takeoff_heading(track)
        self.assertAlmostEqual(result, 287.0)

    def test_all_ground_waypoints_returns_none(self):
        """No airborne waypoints → should return None."""
        track = [
            _wp(on_ground=True, true_track=285.0, timestamp=1),
            _wp(on_ground=True, true_track=285.0, timestamp=2),
        ]
        result = runway_inferrer.extract_takeoff_heading(track)
        self.assertIsNone(result)

    def test_empty_track_returns_none(self):
        result = runway_inferrer.extract_takeoff_heading([])
        self.assertIsNone(result)

    def test_airborne_only_no_ground_prefix(self):
        """Track with no ground prefix still returns first heading."""
        track = [
            _wp(on_ground=False, true_track=155.0, timestamp=1),
            _wp(on_ground=False, true_track=140.0, timestamp=2),
        ]
        result = runway_inferrer.extract_takeoff_heading(track)
        self.assertAlmostEqual(result, 155.0)


if __name__ == "__main__":
    unittest.main()
