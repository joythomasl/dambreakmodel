import unittest

from app.avulsion import assess_avulsion
from app.damage import analyze_damage, interpolate_damage_fraction, point_in_polygon


class DamageAvulsionTests(unittest.TestCase):
    def setUp(self):
        self.hazard = {
            "branch": "conditional_secondary_failure",
            "maximum_depth_m": 2.0,
            "maximum_speed_mps": 2.5,
            "duration_hours": 7,
            "extent": {"geometry": {"coordinates": [[[78.2, 30.0], [78.4, 30.0], [78.4, 30.2], [78.2, 30.2], [78.2, 30.0]]]}}
        }

    def test_damage_curve_and_spatial_filter(self):
        self.assertGreater(interpolate_damage_fraction("residential", 2), 0)
        self.assertTrue(point_in_polygon(78.3, 30.1, self.hazard["extent"]["geometry"]["coordinates"][0]))
        assets = [
            {"id":"inside", "name":"Inside", "type":"residential", "lat":30.1, "lon":78.3, "quantity":1, "unit":"building", "unit_cost_inr":1_000_000, "cost_source":"schedule", "confidence":"reviewed"},
            {"id":"outside", "name":"Outside", "type":"residential", "lat":31.1, "lon":79.3, "quantity":1, "unit":"building", "unit_cost_inr":1_000_000, "cost_source":"schedule", "confidence":"reviewed"},
        ]
        result = analyze_damage(assets, self.hazard)
        self.assertEqual(1, result["unique_assets_assessed"])
        self.assertEqual("inside", result["items"][0]["asset_id"])

    def test_avulsion_requires_evidence_and_ranks_candidate(self):
        self.assertEqual("not_assessed", assess_avulsion([], self.hazard)["status"])
        candidate = {
            "id":"p1", "name":"Alternative swale", "current_channel_elevation_m":410,
            "candidate_elevation_m":407, "slope_current":0.005, "slope_candidate":0.012,
            "distance_to_channel_m":120, "evidence_source":"conditioned DEM", "source_url":"https://example.org/dem"
        }
        result = assess_avulsion([candidate], self.hazard)
        self.assertEqual("screened", result["status"])
        self.assertGreater(result["candidates"][0]["score"], 0)


if __name__ == "__main__":
    unittest.main()
