import unittest
import json
from opensky_client import StateVector
from weather_client import WindObs
from datetime import datetime, timezone
from flight_enricher import FlightEnrichment
import record_builder

class TestRecordBuilder(unittest.TestCase):
    def _make_sv(self):
        return StateVector(
            icao24="a1b2c3",
            callsign="SWA1234",
            longitude=-76.7100,
            latitude=39.2100,
            altitude_m=975.36, # ~3200 ft
            velocity_mps=126.0,
            true_track=260.0,   # mid-flight heading (post-SID turn) — NOT the takeoff heading
            on_ground=False,
            timestamp=1600000000
        )

    def _make_wind(self):
        return WindObs(
            direction_deg=270,
            speed_kt=12,
            gust_kt=18,
            raw_metar="KBWI 051254Z 27012G18KT 10SM FEW040 22/10 A2992",
            observed_at=datetime.now(timezone.utc)
        )

    def _make_enrichment(self):
        return FlightEnrichment(
            aircraft_type="B738",
            aircraft_model="Boeing 737-800",
            destination="FLL",
            route="BWI ⟶ FLL"
        )

    def test_record_building_with_historical_track(self):
        """Runway inferred from historical takeoff heading (283°), not the live flyover track (260°)."""
        sv = self._make_sv()
        wind = self._make_wind()
        enrichment = self._make_enrichment()

        record = record_builder.build(
            sv, "28", "28 (West)", wind, enrichment,
            takeoff_heading_deg=281.4,
            heading_source="historical_track",
        )
        self.assertEqual(record.flight_number, "SWA1234")
        self.assertEqual(record.icao24, "a1b2c3")
        self.assertEqual(record.aircraft_type, "B738")
        self.assertEqual(record.aircraft_model, "Boeing 737-800")
        self.assertEqual(record.destination, "FLL")
        self.assertEqual(record.route, "BWI ⟶ FLL")
        self.assertEqual(record.altitude_ft, 3200)
        self.assertAlmostEqual(record.flyover_track_deg, 260.0)    # live heading at flyover
        self.assertAlmostEqual(record.takeoff_heading_deg, 281.4)  # historical liftoff heading
        self.assertEqual(record.heading_source, "historical_track")
        self.assertEqual(record.runway, "28")
        self.assertEqual(record.runway_direction, "28 (West)")
        self.assertEqual(record.wind_direction_deg, 270)
        self.assertEqual(record.wind_speed_kt, 12)
        self.assertEqual(record.wind_gust_kt, 18)

    def test_record_building_with_flyover_fallback(self):
        """When no historical track is available, takeoff_heading_deg is None and source is flyover_fallback."""
        sv = self._make_sv()
        wind = self._make_wind()

        record = record_builder.build(
            sv, "UNKNOWN", "Unknown direction", wind, None,
            takeoff_heading_deg=None,
            heading_source="flyover_fallback",
        )
        self.assertIsNone(record.takeoff_heading_deg)
        self.assertEqual(record.heading_source, "flyover_fallback")
        self.assertAlmostEqual(record.flyover_track_deg, 260.0)

    def test_json_serialization(self):
        sv = self._make_sv()
        wind = self._make_wind()
        enrichment = self._make_enrichment()

        record = record_builder.build(
            sv, "28", "28 (West)", wind, enrichment,
            takeoff_heading_deg=281.4,
            heading_source="historical_track",
        )
        json_str = record_builder.to_json_line(record)
        data = json.loads(json_str)
        self.assertEqual(data["flight_number"], "SWA1234")
        self.assertEqual(data["aircraft_type"], "B738")
        self.assertEqual(data["destination"], "FLL")
        self.assertEqual(data["altitude_ft"], 3200)
        self.assertAlmostEqual(data["flyover_track_deg"], 260.0)
        self.assertAlmostEqual(data["takeoff_heading_deg"], 281.4)
        self.assertEqual(data["heading_source"], "historical_track")

if __name__ == "__main__":
    unittest.main()
