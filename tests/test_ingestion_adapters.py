import json
import tempfile
import unittest
from pathlib import Path

from app.ingestion import IngestionError, parse_standard_timeseries, validate_upload
from app.model_adapters import DFlowFMAdapter, DualSPHysicsAdapter, parse_hydrograph_csv


class IngestionAdapterTests(unittest.TestCase):
    def test_timeseries_schema(self):
        csv_data = (
            "site_id,time,variable,value,unit,source,source_url,quality\n"
            "tehri,2026-09-29T10:00:00+05:30,reservoir_storage,2500,MCM,CWC,https://example.org,official\n"
        ).encode()
        rows = parse_standard_timeseries(csv_data)
        self.assertEqual(2500.0, rows[0]["value"])
        self.assertTrue(validate_upload("input.csv", csv_data)["valid"])

    def test_invalid_extension_is_rejected(self):
        with self.assertRaises(IngestionError):
            validate_upload("payload.exe", b"not allowed")

    def test_solver_adapters_prepare_truthful_packages(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sph = DualSPHysicsAdapter().prepare(root / "sph", {"event_type":"dam_breach"})
            self.assertEqual("input package only", sph["status"])
            points = [{"time":"2026-09-29T00:00:00+00:00", "flow_cumecs":12.0}]
            dflow = DFlowFMAdapter().prepare(root / "dflow", points)
            self.assertEqual(points, parse_hydrograph_csv(root / "dflow" / dflow["boundary"]))
            self.assertEqual("not_run", DFlowFMAdapter().run(root / "missing.mdu")["status"])


if __name__ == "__main__":
    unittest.main()
