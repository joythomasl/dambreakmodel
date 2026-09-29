from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.catalog import load_site, public_catalog
from app.exports import create_exports
from app.scenario import load_demo, run_demo_scenario
from app.state import observation_gate

PRESETS = {
    "tehri_breach": {"event_type": "dam_breach", "breach_width_m": 60, "breach_depth_m": 30, "formation_hours": 1.5, "rainfall_multiplier": 1.0},
    "extreme_monsoon": {"event_type": "dam_breach", "breach_width_m": 80, "breach_depth_m": 35, "formation_hours": 0.75, "rainfall_multiplier": 1.3},
    "lake_outburst": {"event_type": "lake_burst", "breach_width_m": 42, "breach_depth_m": 24, "formation_hours": 0.6, "rainfall_multiplier": 1.15},
    "blockage_failure": {"event_type": "blockage_failure", "breach_width_m": 55, "breach_depth_m": 22, "formation_hours": 1.0, "rainfall_multiplier": 1.2},
    "sudden_release": {"event_type": "sudden_release", "breach_width_m": 28, "breach_depth_m": 14, "formation_hours": 4.0, "rainfall_multiplier": 0.9},
}


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def demo_payload() -> dict:
    demo = load_demo()
    return {
        "mode": "offline_demo",
        "id": demo["id"],
        "label": demo["label"],
        "description": demo["description"],
        "fixed_time_basis": demo["fixed_time_basis"],
        "observations": demo["observations"],
        "rainfall": demo["rainfall"],
        "assets": demo["assets"],
        "gate": {
            "ready": True,
            "mode": "offline_demo",
            "message": "Packaged synthetic fixture ready; values are not current observations.",
            "checks": {
                "reservoir_state": {"ready": True, "sites": ["tehri", "koteshwar"], "required": ["tehri", "koteshwar"], "synthetic": True},
                "rainfall": {"ready": True, "records": len(demo["rainfall"]), "minimum_records": 3, "synthetic": True},
                "exposure": {"ready": True, "records": len(demo["assets"]), "synthetic": True},
            },
        },
        "sources": [{
            "source_id": "github_pages_demo",
            "name": "Packaged synthetic fixture",
            "status": "demo",
            "message": "Invented hydrology, assets and cost rates. Real Indian site names and chain; no external request.",
            "observed_at": None,
        }],
    }


def build(output: Path) -> None:
    output = output.resolve()
    if output == ROOT.resolve() or ROOT.resolve() not in output.parents:
        raise ValueError("Pages output must be a dedicated directory inside the repository")
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)

    shutil.copytree(ROOT / "app" / "static", output / "static")
    html = (ROOT / "app" / "static" / "index.html").read_text(encoding="utf-8")
    pages_scripts = '  <script>window.HYDRA_STATIC_SITE=true;</script>\n  <script src="./static/pages-api.js"></script>\n'
    html = html.replace('  <script src="./static/app.js"></script>\n', pages_scripts + '  <script src="./static/app.js"></script>\n')
    (output / "index.html").write_text(html, encoding="utf-8")
    (output / ".nojekyll").write_text("", encoding="utf-8")

    site = load_site()
    empty_gate = observation_gate(site, [], [], [])
    write_json(output / "pages-data" / "catalog.json", public_catalog(site))
    write_json(output / "pages-data" / "state.json", {"observations": [], "rainfall": [], "assets": [], "gate": empty_gate})
    write_json(output / "pages-data" / "sources.json", {
        "sources": [{
            "source_id": "github_pages",
            "name": "GitHub Pages packaged deployment",
            "status": "cached",
            "message": "Choose a demonstration preset. Live feeds require the local Python application.",
            "observed_at": None,
        }],
        "auto_ingested": {"observations": 0, "rainfall": 0},
        "gate": empty_gate,
    })
    write_json(output / "pages-data" / "demo.json", demo_payload())

    for name, config in PRESETS.items():
        result = run_demo_scenario(config)
        generated = create_exports(result)
        deployed_exports = {}
        export_dir = output / "pages-data" / "exports" / name
        export_dir.mkdir(parents=True, exist_ok=True)
        for export_name, relative_source in generated.items():
            source = ROOT / relative_source
            destination = export_dir / source.name
            shutil.copy2(source, destination)
            deployed_exports[export_name] = f"./pages-data/exports/{name}/{source.name}"
        result["exports"] = deployed_exports
        write_json(output / "pages-data" / "scenarios" / f"{name}.json", result)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the HYDRA GitHub Pages deployment")
    parser.add_argument("--output", type=Path, default=ROOT / "_site")
    args = parser.parse_args()
    build(args.output if args.output.is_absolute() else ROOT / args.output)


if __name__ == "__main__":
    main()
