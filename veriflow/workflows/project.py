from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from veriflow import __version__
from veriflow.core.backends.registry import (
    get_connectivity_backend,
    get_simulation_backend,
    get_synthesis_backend,
)
from veriflow.core.run_id import get_next_run_id
from veriflow.core.stages.connectivity import InterfaceStage
from veriflow.core.stages.simulation import SimulationStage
from veriflow.core.stages.synthesis import SynthesisStage
from veriflow.framework import Design, Flow, RunRequest, RunResult
from veriflow.generators.results import generate_results_json
from veriflow.models.execution_profile import ExecutionProfile
from veriflow.models.interface_profile import get_interface_profile
from veriflow.workflows.project_config import ProjectWorkflowConfig


@dataclass
class ProjectRunResult:
    run_dir: Path
    result: RunResult


def _rel_to_root(path: Path, root: Path) -> str:
    """Render *path* relative to *root* (the veriflow.yaml directory) so the
    results.json stays portable if the project folder is moved."""
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def _stage_entry(
    result: RunResult,
    name: str,
    run_dir: Path,
    root: Path,
    *,
    with_waves: bool = False,
) -> dict:
    """Build the results.json entry for one stage.

    A stage absent from result.stages means it wasn't configured (e.g. no
    `interface:` section, no tb_sources) -- treated the same as SKIPPED.
    """
    sr = result.stages.get(name)
    if sr is None:
        entry: dict = {"status": "SKIPPED", "log": None}
        if with_waves:
            entry["waves"] = None
        return entry

    # Simulation backends report "COMPLETED" (no pass/fail concept of their
    # own); normalize to "PASS" for consistency with the other stages and
    # with Database Mode's show-run/list-runs/db run (same fix applied there).
    status = "PASS" if sr.status == "COMPLETED" else sr.status

    log = _rel_to_root(run_dir / sr.log_paths[0], root) if sr.log_paths else None
    entry = {"status": status, "log": log}

    if with_waves:
        waves = None
        if sr.artifacts and sr.artifacts.get("wave"):
            waves = _rel_to_root(run_dir / sr.artifacts["wave"][0], root)
        entry["waves"] = waves

    return entry


def _compute_rtl_hash(rtl_sources: list[Path]) -> dict[str, str]:
    """sha256 (hex) of each RTL source's on-disk content, keyed by filename.

    This is the traceability snapshot: if the RTL is edited after a run
    completes, the recorded hash no longer matches the file. Files that no
    longer exist are silently skipped rather than raising -- results.json
    generation shouldn't fail just because a source vanished after the
    stages that actually needed it already ran successfully.
    """
    hashes: dict[str, str] = {}
    for p in rtl_sources:
        if not p.exists():
            continue
        hashes[p.name] = hashlib.sha256(p.read_bytes()).hexdigest()
    return hashes


def _write_results_json(
    config: ProjectWorkflowConfig,
    run_dir: Path,
    design: Design,
    result: RunResult,
) -> None:
    root = config.root

    data = {
        "schema_version": "1.0",
        "status": result.status,
        "command": "project run",
        "run_dir": _rel_to_root(run_dir, root),
        "interface_name": config.interface.name if config.interface else None,
        "top_module": design.top_module,
        "rtl_sources": [_rel_to_root(p, root) for p in design.rtl_sources],
        "tb_sources": [_rel_to_root(p, root) for p in design.tb_sources],
        "technology": config.technology.name,
        "stages": {
            "connectivity": _stage_entry(result, "connectivity", run_dir, root),
            "simulation": _stage_entry(result, "simulation", run_dir, root, with_waves=True),
            "synthesis": _stage_entry(result, "synthesis", run_dir, root),
        },
        "rtl_hash": _compute_rtl_hash(design.rtl_sources),
        "veriflow_version": __version__,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    generate_results_json(data, run_dir / "results.json")


def build_project_flow(
    config: ProjectWorkflowConfig,
) -> tuple[Design, Flow]:
    design = Design(
        top_module=config.top_module,
        rtl_sources=config.rtl_sources,
        tb_sources=config.tb_sources,
    )

    profile = ExecutionProfile(
        connectivity_backend=config.execution.connectivity_backend,
        simulation_backend=config.execution.simulation_backend,
        synthesis_backend=config.execution.synthesis_backend,
        technology_name=config.technology.name,
    )

    stages = []

    if config.interface is not None:
        stages.append(
            InterfaceStage(
                interface_profile=get_interface_profile(config.interface.name),
                profile=profile,
                backend=get_connectivity_backend(profile.connectivity_backend),
            )
        )

    if config.tb_sources:
        stages.append(
            SimulationStage(
                tb_top=config.tb_top,
                profile=profile,
                backend=get_simulation_backend(profile.simulation_backend),
            )
        )

    stages.append(
        SynthesisStage(
            profile=profile,
            backend=get_synthesis_backend(profile.synthesis_backend),
        )
    )

    return design, Flow(stages)


class ProjectWorkflow:
    def __init__(
        self,
        config: ProjectWorkflowConfig,
    ) -> None:
        self.config = config

    @classmethod
    def from_file(
        cls,
        path: Path | str,
    ) -> "ProjectWorkflow":
        return cls(ProjectWorkflowConfig.from_file(path))

    def run(
        self,
        request: RunRequest | None = None,
    ) -> ProjectRunResult:
        design, flow = build_project_flow(self.config)

        if request is None:
            run_dir = self.config.runs_dir / get_next_run_id(self.config.runs_dir)
            run_dir.mkdir(parents=True, exist_ok=True)
            request = RunRequest(work_dir=run_dir)
        else:
            run_dir = request.work_dir
            run_dir.mkdir(parents=True, exist_ok=True)

        result = flow.run(design, request)

        _write_results_json(self.config, run_dir, design, result)

        return ProjectRunResult(run_dir=run_dir, result=result)
