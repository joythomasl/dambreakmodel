import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

import app.exports as exports_module
import app.scenario as scenario_module
import app.state as state_module
from app.exports import create_exports
from app.scenario import run_online_scenario


class ScenarioIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name)
        self.old_state = state_module.STATE_DIR
        self.old_scenarios = scenario_module.SCENARIO_DIR
        self.old_export_scenarios = exports_module.SCENARIO_DIR
        state_module.STATE_DIR = root / "state"
        scenario_module.SCENARIO_DIR = root / "runtime" / "scenarios"
        exports_module.SCENARIO_DIR = root / "runtime" / "scenarios"

    def tearDown(self):
        state_module.STATE_DIR = self.old_state
        scenario_module.SCENARIO_DIR = self.old_scenarios
        exports_module.SCENARIO_DIR = self.old_export_scenarios
        self.temporary.cleanup()

    def test_online_gated_scenario_and_exports(self):
        now = datetime.now(timezone.utc)
        observations = [
            {"site_id":"tehri", "variable":"reservoir_storage", "value":2500, "unit":"MCM", "observed_at":now.isoformat(), "source":"official test fixture", "source_url":"https://example.org", "quality":"test"},
            {"site_id":"koteshwar", "variable":"reservoir_storage", "value":30, "unit":"MCM", "observed_at":now.isoformat(), "source":"official test fixture", "source_url":"https://example.org", "quality":"test"},
        ]
        rainfall = [
            {"site_id":"upstream", "time":(now - timedelta(hours=2-i)).isoformat(), "variable":"rainfall", "value":value, "unit":"mm", "source":"official test fixture", "source_url":"https://example.org", "quality":"test"}
            for i, value in enumerate((2, 4, 3))
        ]
        assets = [{
            "id":"hospital", "name":"Hospital", "type":"critical_facility", "lat":30.092, "lon":78.278,
            "quantity":1, "unit":"facility", "unit_cost_inr":50_000_000, "cost_source":"test schedule",
            "source_url":"https://example.org", "confidence":"test fixture", "people":100,
        }]
        state_module.save_state("observations", observations)
        state_module.save_state("rainfall", rainfall)
        state_module.save_state("assets", assets)
        result = run_online_scenario({"breach_width_m":45})
        repeated = run_online_scenario({"breach_width_m":45})
        self.assertEqual(result["id"], repeated["id"])
        self.assertEqual({"no_secondary_failure", "conditional_secondary_failure"}, set(result["cascade"]["branches"]))
        self.assertEqual("input package only", result["model_status"]["sph"]["status"])
        exported = create_exports(result)
        self.assertEqual({"geojson", "kml", "shapefile", "geotiff", "simulation_json", "pdf", "manifest"}, set(exported))
        for relative in exported.values():
            self.assertTrue((Path(self.temporary.name) / relative).exists())


if __name__ == "__main__":
    unittest.main()
