import unittest
from weather_client import parse_metar_wind

class TestWeatherClient(unittest.TestCase):
    def test_parse_metar_standard(self):
        raw = "KBWI 051254Z 27012KT 10SM FEW040 22/10 A2992"
        wind = parse_metar_wind(raw)
        self.assertEqual(wind.direction_deg, 270)
        self.assertEqual(wind.speed_kt, 12)
        self.assertIsNone(wind.gust_kt)

    def test_parse_metar_with_gusts(self):
        raw = "KBWI 051254Z 27012G18KT 10SM FEW040 22/10 A2992"
        wind = parse_metar_wind(raw)
        self.assertEqual(wind.direction_deg, 270)
        self.assertEqual(wind.speed_kt, 12)
        self.assertEqual(wind.gust_kt, 18)

    def test_parse_metar_variable(self):
        raw = "KBWI 051254Z VRB04KT 10SM CLR 20/08 A3000"
        wind = parse_metar_wind(raw)
        self.assertEqual(wind.direction_deg, 0)
        self.assertEqual(wind.speed_kt, 4)

if __name__ == "__main__":
    unittest.main()
