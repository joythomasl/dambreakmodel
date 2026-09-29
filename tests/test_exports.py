import json
import struct
import tempfile
import unittest
import zipfile
from pathlib import Path

from app.exports import (_format_inr, _indian_integer, write_geojson, write_geotiff,
                         write_kml, write_pdf, write_shapefile_zip)


def result_fixture():
    branches = {}
    damage = {}
    for name, depth, peak in (("no_secondary_failure", 1.2, 900), ("conditional_secondary_failure", 2.3, 1700)):
        extent = {"type":"Feature", "properties":{"branch":name, "maximum_depth_m":depth}, "geometry":{"type":"Polygon", "coordinates":[[[78.2,30.0],[78.3,30.0],[78.3,30.1],[78.2,30.1],[78.2,30.0]]]}}
        branches[name] = {"rishikesh_hazard":{"extent":extent, "arrival_time":"2026-09-29T00:00:00+00:00", "peak_flow_cumecs":peak, "maximum_depth_m":depth, "maximum_speed_mps":2, "duration_hours":4}}
        damage[name] = {"people_potentially_exposed":10, "totals":{"central_inr":1000}}
    return {
        "id":"fixture", "site":{"name":"Tehri chain"}, "config":{"event_type":"dam_breach"},
        "cascade":{"branches":branches}, "damage":damage,
        "warnings":["screening only"], "input_gate":{"checks":{"rainfall":{"ready":True}}},
        "manifest":{"source":"test fixture"},
    }


class ExportTests(unittest.TestCase):
    def test_all_export_writers(self):
        result = result_fixture()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            geojson, kml, shp, tif, pdf = (root / name for name in ("extent.geojson", "extent.kml", "extent.zip", "depth.tif", "report.pdf"))
            write_geojson(geojson, result)
            write_kml(kml, result)
            write_shapefile_zip(shp, result)
            write_geotiff(tif, result)
            write_pdf(pdf, result)
            self.assertEqual("FeatureCollection", json.loads(geojson.read_text())["type"])
            self.assertIn("<kml", kml.read_text())
            with zipfile.ZipFile(shp) as archive:
                self.assertEqual({"flood_extent.shp", "flood_extent.shx", "flood_extent.dbf", "flood_extent.prj"}, set(archive.namelist()))
            self.assertEqual(b"II*\x00", tif.read_bytes()[:4])
            data = tif.read_bytes()
            ifd_offset = struct.unpack_from("<I", data, 4)[0]
            entry_count = struct.unpack_from("<H", data, ifd_offset)[0]
            tags = {}
            for index in range(entry_count):
                tag, field_type, count = struct.unpack_from("<HHI", data, ifd_offset + 2 + index * 12)
                raw = data[ifd_offset + 10 + index * 12:ifd_offset + 14 + index * 12]
                tags[tag] = (field_type, count, raw)
            self.assertEqual(32, struct.unpack("<H", tags[258][2][:2])[0])
            self.assertEqual(3, struct.unpack("<H", tags[339][2][:2])[0])
            description_offset = struct.unpack("<I", tags[270][2])[0]
            description = data[description_offset:description_offset + tags[270][1]]
            self.assertIn(b"unit=metre (m)", description)
            self.assertEqual(b"%PDF", pdf.read_bytes()[:4])

    def test_indian_currency_scale_and_grouping(self):
        self.assertEqual("1,23,45,678", _indian_integer(12_345_678))
        self.assertEqual("INR 1.23 crore (1,23,45,678)", _format_inr(12_345_678))
        self.assertEqual("INR 2.50 lakh (2,50,000)", _format_inr(250_000))


if __name__ == "__main__":
    unittest.main()
