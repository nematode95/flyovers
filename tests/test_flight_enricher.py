import unittest
from unittest.mock import patch, MagicMock
import flight_enricher

class TestFlightEnricher(unittest.TestCase):
    @patch("flight_enricher.requests.get")
    def test_get_aircraft_info_success(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "ICAOTypeCode": "B738",
            "Manufacturer": "Boeing",
            "Type": "737-800"
        }
        mock_get.return_value = mock_resp

        ac_type, ac_model = flight_enricher.get_aircraft_info("A1B2C3")
        self.assertEqual(ac_type, "B738")
        self.assertIn("Boeing", ac_model)

    @patch("flight_enricher.requests.get")
    def test_get_aircraft_info_failure(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_get.return_value = mock_resp

        ac_type, ac_model = flight_enricher.get_aircraft_info("UNKNOWN_HEX")
        self.assertEqual(ac_type, "UNKNOWN")
        self.assertEqual(ac_model, "Unknown Aircraft")

    @patch("flight_enricher.requests.get")
    def test_get_route_info_success(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "results": [
                {
                    "detail": {
                        "schd_from": "BWI",
                        "schd_to": "FLL",
                        "route": "Baltimore (BWI) ⟶ Fort Lauderdale (FLL)"
                    }
                }
            ]
        }
        mock_get.return_value = mock_resp

        dest, route = flight_enricher.get_route_info("SWA1234")
        self.assertEqual(dest, "FLL")
        self.assertIn("Fort Lauderdale", route)

    def test_enrich_flight_empty_inputs(self):
        enrichment = flight_enricher.enrich_flight("", "")
        self.assertEqual(enrichment.aircraft_type, "UNKNOWN")
        self.assertEqual(enrichment.destination, "UNKNOWN")

if __name__ == "__main__":
    unittest.main()
