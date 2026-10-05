import unittest
import json
from opensky_client import StateVector
from weather_client import WindObs
from datetime import datetime, timezone
import record_builder

class TestRecordBuilder(unittest.TestCase):
    def test_record_building_and_json(self):
        sv = StateVector(
            icao24="a1b2c3",
            callsign="SWA1234",
            longitude=-76.7100,
            latitude=39.2100,
            altitude_m=975.36, # ~3200 ft
            velocity_mps=126.0,
            true_track=281.4,
            on_ground=False,
            timestamp=1600000000
        )
        wind = WindObs(
            direction_deg=270,
            speed_kt=12,
            gust_kt=18,
            raw_metar="KBWI 051254Z 27012G18KT 10SM FEW040 22/10 A2992",
            observed_at=datetime.now(timezone.utc)
        )

        record = record_builder.build(sv, "28", "28 (West)", wind)
        self.assertEqual(record.flight_number, "SWA1234")
        self.assertEqual(record.icao24, "a1b2c3")
        self.assertEqual(record.altitude_ft, 3200)
        self.assertEqual(record.true_track_deg, 281.4)
        self.assertEqual(record.runway, "28")
        self.assertEqual(record.runway_direction, "28 (West)")
        self.assertEqual(record.wind_direction_deg, 270)
        self.assertEqual(record.wind_speed_kt, 12)
        self.assertEqual(record.wind_gust_kt, 18)

        json_str = record_builder.to_json_line(record)
        data = json.loads(json_str)
        self.assertEqual(data["flight_number"], "SWA1234")
        self.assertEqual(data["altitude_ft"], 3200)
        self.assertEqual(data["runway"], "28")

if __name__ == "__main__":
    unittest.main()
