import unittest
import runway_inferrer

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

if __name__ == "__main__":
    unittest.main()
