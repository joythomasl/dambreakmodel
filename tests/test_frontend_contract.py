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
        self.assertIn('<script src="./static/simulation3d.js"></script>', html)
        self.assertIn('window.Simulation3D', javascript)
        self.assertIn('simulationDomain', javascript)
        self.assertIn('loadSatellite', javascript)
        self.assertIn('buildMapContext', javascript)
        self.assertIn('regionalSimulation', javascript)

    def test_github_pages_adapter_and_workflow_are_present(self):
        html = (ROOT / "app" / "static" / "index.html").read_text(encoding="utf-8")
        app_javascript = (ROOT / "app" / "static" / "app.js").read_text(encoding="utf-8")
        pages_javascript = (ROOT / "app" / "static" / "pages-api.js").read_text(encoding="utf-8")
        builder = (ROOT / "tools" / "build_pages.py").read_text(encoding="utf-8")
        workflow = (ROOT / ".github" / "workflows" / "pages.yml").read_text(encoding="utf-8")
        self.assertIn('href="./static/styles.css"', html)
        self.assertIn("window.HYDRA_STATIC_API", app_javascript)
        self.assertIn("window.HYDRA_STATIC_SITE", pages_javascript)
        self.assertIn("pages-data", pages_javascript)
        self.assertIn("PRESETS", builder)
        self.assertIn("actions/deploy-pages@v4", workflow)


if __name__ == "__main__":
    unittest.main()
