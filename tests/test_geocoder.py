import unittest
from unittest.mock import patch, MagicMock
import geocoder

class TestGeocoder(unittest.TestCase):
    def test_geocode_empty_address(self):
        with self.assertRaises(ValueError):
            geocoder.geocode_address("")

    @patch("geocoder.requests.get")
    def test_geocode_success(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [{"lat": "39.2100", "lon": "-76.7100"}]
        mock_get.return_value = mock_resp

        lat, lon = geocoder.geocode_address("123 Main St, Elkridge, MD 21075")
        self.assertAlmostEqual(lat, 39.2100)
        self.assertAlmostEqual(lon, -76.7100)

    @patch("geocoder.requests.get")
    def test_geocode_not_found(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = []
        mock_get.return_value = mock_resp

        with self.assertRaises(ValueError):
            geocoder.geocode_address("Nonexistent Place 99999")

if __name__ == "__main__":
    unittest.main()
