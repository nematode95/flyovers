import unittest
from opensky_client import StateVector
from config import Settings
import flyover_detector

class TestFlyoverDetector(unittest.TestCase):
    def setUp(self):
        self.settings = Settings(
            opensky_client_id="",
            opensky_client_secret="",
            listen_address="123 Main St, Elkridge, MD 21075",
            listen_lat=39.2100,
            listen_lon=-76.7100,
            flyover_radius_nm=1.0,
            bbox={},
            poll_interval_sec=30
        )

    def test_haversine_same_point(self):
        dist = flyover_detector.haversine_nm(39.2100, -76.7100, 39.2100, -76.7100)
        self.assertAlmostEqual(dist, 0.0, places=4)

    def test_haversine_known_distance(self):
        # Point ~0.01 deg north (~0.6 nm)
        dist = flyover_detector.haversine_nm(39.2100, -76.7100, 39.2200, -76.7100)
        self.assertGreater(dist, 0.5)
        self.assertLess(dist, 0.7)

    def test_is_flyover_valid(self):
        sv = StateVector(
            icao24="a1b2c3",
            callsign="SWA1234",
            longitude=-76.7105,
            latitude=39.2105,
            altitude_m=1000.0, # ~3280 ft
            velocity_mps=120.0,
            true_track=285.0,
            on_ground=False,
            timestamp=1600000000
        )
        self.assertTrue(flyover_detector.is_flyover(sv, self.settings))

    def test_is_flyover_on_ground(self):
        sv = StateVector(
            icao24="a1b2c3",
            callsign="SWA1234",
            longitude=-76.7105,
            latitude=39.2105,
            altitude_m=1000.0,
            velocity_mps=0.0,
            true_track=285.0,
            on_ground=True,
            timestamp=1600000000
        )
        self.assertFalse(flyover_detector.is_flyover(sv, self.settings))

    def test_is_flyover_altitude_out_of_bounds(self):
        # Too low (< 500 ft)
        sv_low = StateVector(
            icao24="a1b2c3", callsign="SWA1234", longitude=-76.7105, latitude=39.2105,
            altitude_m=100.0, velocity_mps=120.0, true_track=285.0, on_ground=False, timestamp=1600000000
        )
        self.assertFalse(flyover_detector.is_flyover(sv_low, self.settings))

        # Too high (> 10,000 ft)
        sv_high = StateVector(
            icao24="a1b2c3", callsign="SWA1234", longitude=-76.7105, latitude=39.2105,
            altitude_m=4000.0, velocity_mps=120.0, true_track=285.0, on_ground=False, timestamp=1600000000
        )
        self.assertFalse(flyover_detector.is_flyover(sv_high, self.settings))

    def test_is_flyover_non_commercial_callsign(self):
        # General aviation / N-number callsign
        sv = StateVector(
            icao24="a1b2c3", callsign="N12345", longitude=-76.7105, latitude=39.2105,
            altitude_m=1000.0, velocity_mps=120.0, true_track=285.0, on_ground=False, timestamp=1600000000
        )
        self.assertFalse(flyover_detector.is_flyover(sv, self.settings))

    def test_is_flyover_outside_radius(self):
        # ~10 nm away
        sv = StateVector(
            icao24="a1b2c3", callsign="SWA1234", longitude=-76.5000, latitude=39.2100,
            altitude_m=1000.0, velocity_mps=120.0, true_track=285.0, on_ground=False, timestamp=1600000000
        )
        self.assertFalse(flyover_detector.is_flyover(sv, self.settings))

if __name__ == "__main__":
    unittest.main()
