import json
import tempfile
import unittest
from pathlib import Path

from app.damage import analyze_grid_damage
from app.exports import write_geojson
from app.inundation import load_structures, load_terrain, simulate_inundation


TIME = "2026-09-29T00:00:00+00:00"
HYDROGRAPH = [
    {"time": TIME, "flow_cumecs": 20.0},
    {"time": "2026-09-29T01:00:00+00:00", "flow_cumecs": 20.0},
]


class InundationTests(unittest.TestCase):
    def test_local_and_regional_visual_context_is_cached_and_attributed(self):
        root = Path(__file__).resolve().parents[1]
        local = json.loads((root / "app" / "data" / "rishikesh_context.json").read_text(encoding="utf-8"))
        regional = json.loads((root / "app" / "data" / "tehri_rishikesh_context.json").read_text(encoding="utf-8"))
        terrain = json.loads((root / "app" / "data" / "tehri_rishikesh_terrain.json").read_text(encoding="utf-8"))

        self.assertGreaterEqual(len(local["roads"]), 500)
        self.assertGreaterEqual(len(local["labels"]), 10)
        self.assertIn("Sentinel-2", local["satellite"]["source"])
        self.assertIn("CC BY-NC-SA", local["satellite"]["license"])
        self.assertTrue((root / "app" / "static" / local["satellite"]["url"].removeprefix("/static/")).is_file())

        self.assertEqual(["tehri", "koteshwar", "devprayag", "rishikesh"],
                         [node["id"] for node in regional["cascade_nodes"]])
        self.assertGreaterEqual(len(regional["roads"]), 200)
        self.assertGreaterEqual(len(regional["waterways"]), 10)
        self.assertEqual(terrain["width"] * terrain["height"], len(terrain["elevation_m"]))
        self.assertGreater(max(terrain["elevation_m"]), min(terrain["elevation_m"]))
        self.assertTrue((root / "app" / "static" / terrain["satellite"]["url"].removeprefix("/static/")).is_file())

    def test_public_terrain_is_reproducible_and_georeferenced(self):
        terrain = load_terrain()
        self.assertEqual("EPSG:4326", terrain["coordinate_system"])
        self.assertEqual(72, terrain["width"])
        self.assertEqual(48, terrain["height"])
        self.assertEqual(50.0, terrain["cell_size_m"])
        self.assertEqual(1, len(terrain["tiles"]))
        self.assertIn("elevation-tiles-prod", terrain["tiles"][0])

    def test_real_structure_cache_is_attributed_and_inside_terrain(self):
        terrain = load_terrain()
        context = load_structures()
        self.assertEqual("OpenStreetMap contributors", context["source"])
        self.assertIn("ODbL", context["license"])
        self.assertGreater(len(context["structures"]), 0)
        west, north = terrain["west"], terrain["north"]
        east = west + terrain["width"] * terrain["lon_step"]
        south = north - terrain["height"] * terrain["lat_step"]
        for structure in context["structures"]:
            self.assertIn(structure["height_basis"], {"osm_height", "osm_levels_x_3m", "estimated_from_type"})
            for lon, lat in structure["coordinates"]:
                self.assertTrue(west <= lon <= east)
                self.assertTrue(south <= lat <= north)

    def test_2d_solver_moves_water_and_conserves_volume(self):
        terrain = {
            "id": "test-grid", "width": 8, "height": 6, "cell_size_m": 20,
            "elevation_m": [[0.0] * 8 for _ in range(6)],
            "west": 78.0, "north": 30.0, "lon_step": 0.001, "lat_step": 0.001,
            "source": "test terrain",
        }
        low = simulate_inundation(HYDROGRAPH, start_time=TIME, terrain=terrain,
                                  duration_s=600, frame_interval_s=120)
        high_points = [{**point, "flow_cumecs": 40.0} for point in HYDROGRAPH]
        high = simulate_inundation(high_points, start_time=TIME, terrain=terrain,
                                   duration_s=600, frame_interval_s=120)
        self.assertEqual("executed_2d_local_inertial_shallow_water", low["engine"])
        self.assertEqual(6, len(low["frames"]))
        self.assertTrue(all(depth == 0 for depth in low["frames"][0]["depth_m"]))
        self.assertGreater(low["wet_cell_count"], 0)
        self.assertGreater(high["peak_depth_m"], low["peak_depth_m"])
        self.assertLess(abs(low["volume"]["mass_balance_error_m3"]), 0.01)
        self.assertLess(abs(high["volume"]["mass_balance_error_m3"]), 0.01)
        self.assertAlmostEqual(low["volume"]["inflow_m3"], 20 * 600, places=2)

    def test_mapped_channel_routes_water_to_downstream_boundary(self):
        terrain = {
            "id": "channel-test", "width": 8, "height": 10, "cell_size_m": 20,
            "elevation_m": [[10.0] * 8 for _ in range(10)],
            "west": 78.0, "north": 30.0, "lon_step": 0.001, "lat_step": 0.001,
            "source": "test terrain",
        }
        hydrograph = [
            {"time": TIME, "flow_cumecs": 50.0},
            {"time": "2026-09-29T00:10:00+00:00", "flow_cumecs": 50.0},
        ]
        simulation = simulate_inundation(
            hydrograph, start_time=TIME, terrain=terrain, duration_s=600,
            frame_interval_s=120, open_boundaries=["south"],
            channel_coordinates=[[78.004, 30.0], [78.004, 29.991]],
        )
        self.assertTrue(simulation["channel_conditioning"]["applied"])
        self.assertEqual(["south"], simulation["open_boundaries"])
        self.assertTrue(simulation["downstream_reached"])
        self.assertGreater(simulation["downstream_wet_cells"], 0)
        self.assertLessEqual(simulation["downstream_arrival_s"], simulation["duration_s"])
        self.assertLess(abs(simulation["volume"]["mass_balance_error_m3"]), 0.01)

    def test_exported_cells_and_damage_sample_the_same_grid(self):
        terrain = {
            "id": "test-grid", "width": 8, "height": 6, "cell_size_m": 20,
            "elevation_m": [[0.0] * 8 for _ in range(6)],
            "west": 78.0, "north": 30.0, "lon_step": 0.001, "lat_step": 0.001,
            "source": "test terrain",
        }
        simulation = simulate_inundation(HYDROGRAPH, start_time=TIME, terrain=terrain,
                                          duration_s=600, frame_interval_s=120)
        wet_index = next(i for i, depth in enumerate(simulation["maximum_depth_m"]) if depth >= 0.1)
        row, col = divmod(wet_index, 8)
        asset = {"id": "point", "name": "Illustrative point", "type": "residential",
                 "lat": terrain["north"] - (row + 0.5) * terrain["lat_step"],
                 "lon": terrain["west"] + (col + 0.5) * terrain["lon_step"],
                 "quantity": 1, "unit_cost_inr": 100000, "people": 3}
        damage = analyze_grid_damage([asset], simulation)
        self.assertEqual(1, damage["unique_assets_assessed"])
        self.assertGreater(damage["totals"]["central_inr"], 0)
        result = {"mode": "offline_demo", "spatial_simulation": {"no_secondary_failure": simulation}}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cells.geojson"
            write_geojson(path, result)
            features = json.loads(path.read_text(encoding="utf-8"))["features"]
        self.assertEqual(simulation["wet_cell_count"], len(features))
        self.assertTrue(all(feature["properties"]["data_mode"] == "offline_demo" for feature in features))


if __name__ == "__main__":
    unittest.main()
