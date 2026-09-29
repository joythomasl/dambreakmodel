import unittest
from datetime import datetime, timedelta, timezone

from app.cascade import reservoir_response, route_hydrograph
from app.hydrology import create_event_hydrograph, rainfall_runoff


class HydrologyCascadeTests(unittest.TestCase):
    def setUp(self):
        start = datetime(2026, 9, 29, tzinfo=timezone.utc)
        self.rain = [{"time": (start + timedelta(hours=i)).isoformat(), "mm": value} for i, value in enumerate((2, 5, 8, 3))]

    def test_rainfall_runoff_preserves_generated_volume(self):
        result = rainfall_runoff(self.rain, 100.0, 0.5, 0.0, 1)
        expected = 18 / 1000 * 100_000_000 * 0.5
        self.assertAlmostEqual(expected, result["generated_runoff_m3"], places=1)
        self.assertGreater(result["peak_flow_cumecs"], 0)

    def test_event_and_routing_are_deterministic(self):
        event = create_event_hydrograph(self.rain[-1]["time"], "dam_breach", 100, 20, 10, 1)
        routed = route_hydrograph(event["points"], 1.5, 0.9)
        # Per-step flow is rounded to 0.001 cumec before export.
        self.assertAlmostEqual(routed["outgoing_volume_m3"], routed["incoming_volume_m3"] * 0.9, delta=3.0)

    def test_reservoir_mass_balance(self):
        inflow = [{"time": row["time"], "flow_cumecs": 100.0} for row in self.rain]
        result = reservoir_response(
            inflow, initial_storage_mcm=20, capacity_mcm=35, spill_threshold_mcm=33,
            base_release_cumecs=50, max_release_cumecs=700, dead_level_m=580,
            frl_m=612.5, conditional_failure=False, failure_trigger_fraction=0.96,
            breach_release_fraction=0.35,
        )
        self.assertAlmostEqual(0.0, result["mass_balance_error_m3"], places=3)


if __name__ == "__main__":
    unittest.main()
