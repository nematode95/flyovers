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


class TestInferRunwayFromTrack(unittest.TestCase):
    def test_runway_28_departure(self):
        # Runway 28 departure rolling west toward Elkridge
        track = [
            TrackWaypoint(timestamp=1, latitude=39.1730, longitude=-76.6600, altitude_m=30.0, true_track=274.0, on_ground=False),
            TrackWaypoint(timestamp=2, latitude=39.1740, longitude=-76.6800, altitude_m=100.0, true_track=274.0, on_ground=False),
            TrackWaypoint(timestamp=3, latitude=39.1750, longitude=-76.7100, altitude_m=350.0, true_track=275.0, on_ground=False),
        ]
        rwy_id, label, explanation, takeoff_hdg = runway_inferrer.infer_runway_from_track(track)
        self.assertEqual(rwy_id, "28")
        self.assertIn("28", label)
        self.assertIn("Runway 28", explanation)
        self.assertAlmostEqual(takeoff_hdg, 274.0)

    def test_runway_33l_departure(self):
        # Runway 33L departure liftoff near departure end with turn to NW
        track = [
            TrackWaypoint(timestamp=1, latitude=39.1904, longitude=-76.6874, altitude_m=304.0, true_track=310.0, on_ground=False),
            TrackWaypoint(timestamp=2, latitude=39.1934, longitude=-76.6943, altitude_m=304.0, true_track=287.0, on_ground=False),
            TrackWaypoint(timestamp=3, latitude=39.1944, longitude=-76.7011, altitude_m=304.0, true_track=276.0, on_ground=False),
        ]
        rwy_id, label, explanation, takeoff_hdg = runway_inferrer.infer_runway_from_track(track)
        self.assertEqual(rwy_id, "33L")
        self.assertIn("33L", label)
        self.assertIn("Runway 33L", explanation)
        self.assertAlmostEqual(takeoff_hdg, 310.0)

    def test_runway_15r_departure_with_turn(self):
        # Runway 15R rolling southeast, then right climbing turn northwest over Elkridge
        track = [
            TrackWaypoint(timestamp=1, latitude=39.1830, longitude=-76.6790, altitude_m=30.0, true_track=145.0, on_ground=False),
            TrackWaypoint(timestamp=2, latitude=39.1650, longitude=-76.6630, altitude_m=120.0, true_track=144.0, on_ground=False),
            TrackWaypoint(timestamp=3, latitude=39.1500, longitude=-76.6600, altitude_m=300.0, true_track=190.0, on_ground=False),
            TrackWaypoint(timestamp=4, latitude=39.1700, longitude=-76.7100, altitude_m=600.0, true_track=310.0, on_ground=False),
        ]
        rwy_id, label, explanation, takeoff_hdg = runway_inferrer.infer_runway_from_track(track)
        self.assertEqual(rwy_id, "15R")
        self.assertIn("15R", label)
        self.assertIn("right turn", explanation.lower())

    def test_runway_10_departure(self):
        # Runway 10 departure rolling east toward Bay
        track = [
            TrackWaypoint(timestamp=1, latitude=39.1745, longitude=-76.6850, altitude_m=30.0, true_track=94.0, on_ground=False),
            TrackWaypoint(timestamp=2, latitude=39.1735, longitude=-76.6650, altitude_m=150.0, true_track=94.0, on_ground=False),
        ]
        rwy_id, label, explanation, takeoff_hdg = runway_inferrer.infer_runway_from_track(track)
        self.assertEqual(rwy_id, "10")
        self.assertIn("10", label)
        self.assertIn("Runway 10", explanation)

    def test_runway_15l_departure_with_turn(self):
        # Runway 15L (parallel to 15R, eastern side) rolling southeast, then right climbing turn northwest over Elkridge
        track = [
            TrackWaypoint(timestamp=1, latitude=39.1850, longitude=-76.6610, altitude_m=30.0, true_track=144.0, on_ground=False),
            TrackWaypoint(timestamp=2, latitude=39.1780, longitude=-76.6550, altitude_m=120.0, true_track=144.0, on_ground=False),
            TrackWaypoint(timestamp=3, latitude=39.1600, longitude=-76.6500, altitude_m=300.0, true_track=190.0, on_ground=False),
            TrackWaypoint(timestamp=4, latitude=39.1800, longitude=-76.7100, altitude_m=600.0, true_track=310.0, on_ground=False),
        ]
        rwy_id, label, explanation, takeoff_hdg = runway_inferrer.infer_runway_from_track(track)
        self.assertEqual(rwy_id, "15L")
        self.assertIn("15L", label)
        self.assertIn("right turn", explanation.lower())

    def test_runway_10_departure_with_turn(self):
        # Runway 10 departure rolling east toward Bay, then climbing turn back west over Elkridge
        track = [
            TrackWaypoint(timestamp=1, latitude=39.1745, longitude=-76.6850, altitude_m=30.0, true_track=94.0, on_ground=False),
            TrackWaypoint(timestamp=2, latitude=39.1735, longitude=-76.6650, altitude_m=150.0, true_track=94.0, on_ground=False),
            TrackWaypoint(timestamp=3, latitude=39.1800, longitude=-76.6200, altitude_m=450.0, true_track=40.0, on_ground=False),
            TrackWaypoint(timestamp=4, latitude=39.2100, longitude=-76.7200, altitude_m=900.0, true_track=285.0, on_ground=False),
        ]
        rwy_id, label, explanation, takeoff_hdg = runway_inferrer.infer_runway_from_track(track)
        self.assertEqual(rwy_id, "10")
        self.assertIn("10", label)
        self.assertIn("climbing turn", explanation.lower())

    def test_fallback_when_empty_track(self):
        rwy_id, label, explanation, takeoff_hdg = runway_inferrer.infer_runway_from_track([], fallback_heading=283.0)
        self.assertEqual(rwy_id, "28")
        self.assertIn("28", label)
        self.assertIn("inferred from heading", explanation.lower())


if __name__ == "__main__":
    unittest.main()
