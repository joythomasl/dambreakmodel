import unittest
from datetime import datetime, timezone

from app.catalog import load_site, validate_catalog
from app.state import observation_gate


class CatalogStateTests(unittest.TestCase):
    def test_indian_connected_catalog_is_valid(self):
        site = load_site()
        self.assertEqual([], validate_catalog(site))
        self.assertEqual("India", site["basin"]["country"])
        self.assertEqual(["tehri", "koteshwar", "devprayag", "rishikesh"], [node["id"] for node in site["nodes"]])

    def test_gate_requires_storage_at_both_dams_and_current_rain(self):
        site = load_site()
        now = datetime.now(timezone.utc).isoformat()
        observations = [
            {"site_id": "tehri", "variable": "reservoir_storage", "observed_at": now},
            {"site_id": "koteshwar", "variable": "reservoir_storage", "observed_at": now},
        ]
        rainfall = [{"time": now}, {"time": now}, {"time": now}]
        gate = observation_gate(site, observations, rainfall, [{"id": "a"}])
        self.assertTrue(gate["ready"])
        level_only = [{"site_id": "tehri", "variable": "reservoir_level", "observed_at": now}]
        self.assertFalse(observation_gate(site, level_only, rainfall, [{"id": "a"}])["ready"])


if __name__ == "__main__":
    unittest.main()
