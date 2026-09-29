import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class FrontendContractTests(unittest.TestCase):
    def test_javascript_element_ids_exist_in_html(self):
        html = (ROOT / "app" / "static" / "index.html").read_text(encoding="utf-8")
        javascript = (ROOT / "app" / "static" / "app.js").read_text(encoding="utf-8")
        html_ids = set(re.findall(r'\bid="([A-Za-z0-9_-]+)"', html))
        referenced = set(re.findall(r"\$\('([A-Za-z0-9_-]+)'\)", javascript))
        self.assertEqual(set(), referenced - html_ids)

    def test_frontend_has_no_remote_runtime_dependency(self):
        html = (ROOT / "app" / "static" / "index.html").read_text(encoding="utf-8")
        self.assertNotRegex(html, r'<(?:script|link)[^>]+https?://')

    def test_3d_controls_are_present_and_locally_loaded(self):
        html = (ROOT / "app" / "static" / "index.html").read_text(encoding="utf-8")
        javascript = (ROOT / "app" / "static" / "simulation3d.js").read_text(encoding="utf-8")
        html_ids = set(re.findall(r'\bid="([A-Za-z0-9_-]+)"', html))
        referenced = set(re.findall(r"getElementById\('([A-Za-z0-9_-]+)'\)", javascript))
        self.assertEqual(set(), referenced - html_ids)
        self.assertIn('<script src="/static/simulation3d.js"></script>', html)
        self.assertIn('window.Simulation3D', javascript)
        self.assertIn('simulationDomain', javascript)
        self.assertIn('loadSatellite', javascript)
        self.assertIn('buildMapContext', javascript)
        self.assertIn('regionalSimulation', javascript)


if __name__ == "__main__":
    unittest.main()
