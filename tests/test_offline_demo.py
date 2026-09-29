import json
import tempfile
import unittest
import zipfile
from pathlib import Path

import app.exports as exports_module
import app.scenario as scenario_module
import app.state as state_module
from app.exports import create_exports
from app.scenario import ScenarioBlocked, load_demo, run_demo_scenario, run_online_scenario


class OfflineDemoTests(unittest.TestCase):
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

    def test_demo_is_deterministic_labelled_and_separate_from_live_state(self):
        fixture = load_demo()
        self.assertEqual("offline_demo", fixture["mode"])
        self.assertTrue(all(row["quality"] == "synthetic" for row in fixture["observations"] + fixture["rainfall"]))
        first = run_demo_scenario()
        second = run_demo_scenario()
        self.assertEqual(first["id"], second["id"])
        self.assertEqual("offline_demo", first["mode"])
        self.assertIn("SYNTHETIC", first["warnings"][0])
        self.assertEqual("offline_demo", first["manifest"]["mode"])
        self.assertFalse((state_module.STATE_DIR / "observations.json").exists())
        self.assertFalse((state_module.STATE_DIR / "rainfall.json").exists())
        with self.assertRaises(ScenarioBlocked):
            run_online_scenario()

        branches = first["cascade"]["branches"]
        self.assertFalse(branches["no_secondary_failure"]["koteshwar"]["failure_triggered"])
        self.assertTrue(branches["conditional_secondary_failure"]["koteshwar"]["failure_triggered"])
        self.assertGreater(first["cascade"]["comparison"]["additional_damage_central_inr"], 0)
        for branch in branches.values():
            self.assertLess(abs(branch["koteshwar"]["mass_balance_error_m3"]), 1.0)
            timeline = branch["timeline"]
            self.assertLess(timeline[0]["time"], timeline[1]["time"])
            self.assertLess(timeline[1]["time"], timeline[-1]["time"])

    def test_all_demo_exports_carry_synthetic_label(self):
        result = run_demo_scenario()
        files = create_exports(result)
        paths = {key: Path(self.temporary.name) / rel for key, rel in files.items()}
        self.assertTrue(all(path.is_file() for path in paths.values()))
        self.assertTrue(all(path.name.startswith("synthetic_demo_") for key, path in paths.items() if key != "manifest"))
        geojson = json.loads(paths["geojson"].read_text(encoding="utf-8"))
        self.assertTrue(all(feature["properties"]["data_mode"] == "offline_demo" for feature in geojson["features"]))
        self.assertIn("SYNTHETIC DEMO", paths["kml"].read_text(encoding="utf-8"))
        self.assertIn(b"SYNTHETIC DEMONSTRATION", paths["pdf"].read_bytes())
        with zipfile.ZipFile(paths["shapefile"]) as archive:
            dbf_name = next(name for name in archive.namelist() if name.endswith(".dbf"))
            self.assertIn(b"DATA_MODE", archive.read(dbf_name))
            self.assertIn(b"offline_demo", archive.read(dbf_name))


if __name__ == "__main__":
    unittest.main()
