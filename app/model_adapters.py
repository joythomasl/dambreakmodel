from __future__ import annotations

import csv
import json
import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ModelAdapterError(RuntimeError):
    pass


def parse_hydrograph_csv(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    required = {"time", "flow_cumecs"}
    if not rows or not required.issubset(rows[0]):
        raise ModelAdapterError("Hydrograph CSV needs time and flow_cumecs columns")
    return [{"time": row["time"], "flow_cumecs": float(row["flow_cumecs"])} for row in rows]


def write_hydrograph_csv(path: Path, points: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["time", "flow_cumecs"])
        writer.writeheader()
        writer.writerows(points)


class DualSPHysicsAdapter:
    name = "DualSPHysics"

    def __init__(self, binary: str | None = None):
        self.binary = binary or os.getenv("DUALSPHYSICS_BINARY")

    def prepare(self, directory: Path, scenario: dict) -> dict:
        directory.mkdir(parents=True, exist_ok=True)
        manifest = {
            "adapter": self.name,
            "status": "input package only",
            "scenario": scenario,
            "expected_output": "hydrograph.csv with time,flow_cumecs at the hand-off section",
            "note": "A reviewed DualSPHysics geometry/case XML is required for a real solver run."
        }
        (directory / "sph_adapter_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        return manifest

    def run(self, case_path: Path, timeout_seconds: int = 3600) -> dict:
        if not self.binary or not Path(self.binary).exists():
            return {"status":"not_run", "reason":"DUALSPHYSICS_BINARY is not configured", "solver":self.name}
        process = subprocess.run([self.binary, str(case_path)], cwd=str(case_path.parent), capture_output=True, text=True, timeout=timeout_seconds, check=False)
        return {"status":"completed" if process.returncode == 0 else "failed", "returncode":process.returncode, "stdout":process.stdout[-4000:], "stderr":process.stderr[-4000:], "solver":self.name}

class DFlowFMAdapter:
    name = "D-Flow FM"

    def __init__(self, binary: str | None = None):
        self.binary = binary or os.getenv("DFLOWFM_BINARY")

    def prepare(self, directory: Path, hydrograph: list[dict], model_name: str = "tehri_cascade") -> dict:
        directory.mkdir(parents=True, exist_ok=True)
        write_hydrograph_csv(directory / "upstream_boundary.csv", hydrograph)
        mdu = (
            "[model]\n"
            f"Name = {model_name}\n"
            "Program = D-Flow FM\n"
            "[external forcing]\n"
            "UpstreamBoundary = upstream_boundary.csv\n"
            "# Add reviewed mesh, roughness, structures, downstream boundary and vertical datum before running.\n"
        )
        (directory / f"{model_name}.mdu.template").write_text(mdu, encoding="utf-8")
        return {"adapter":self.name, "status":"input package only", "boundary":"upstream_boundary.csv", "model_template":f"{model_name}.mdu.template"}

    def run(self, mdu_path: Path, timeout_seconds: int = 7200) -> dict:
        if not self.binary or not Path(self.binary).exists():
            return {"status":"not_run", "reason":"DFLOWFM_BINARY is not configured", "solver":self.name}
        if mdu_path.name.endswith(".template"):
            return {"status":"not_run", "reason":"Template MDU must be completed and reviewed before solver execution", "solver":self.name}
        process = subprocess.run([self.binary, str(mdu_path)], cwd=str(mdu_path.parent), capture_output=True, text=True, timeout=timeout_seconds, check=False)
        return {"status":"completed" if process.returncode == 0 else "failed", "returncode":process.returncode, "stdout":process.stdout[-4000:], "stderr":process.stderr[-4000:], "solver":self.name}
