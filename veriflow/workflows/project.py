from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
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
from veriflow.core.validator import validate_tools
from veriflow.framework import Design, Flow, RunRequest, RunResult
from veriflow.framework.status import derive_run_status
from veriflow.generators.results import generate_results_json
from veriflow.models.execution_profile import ExecutionProfile
from veriflow.models.interface_profile import get_interface_profile
from veriflow.workflows.project_config import ProjectWorkflowConfig


@dataclass
class ProjectRunResult:
    run_dir: Path
    result: RunResult
    config_warnings: list[str] = field(default_factory=list)


def _rel_to_root(path: Path, root: Path) -> str:
    """Render *path* relative to *root* (the veriflow.yaml directory) so the
    results.json stays portable if the project folder is moved."""
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


_CANONICAL_STAGE_NAMES = ("connectivity", "simulation", "synthesis")


def _effective_stage_status(result: RunResult, name: str, configured_stage_names: frozenset[str]) -> str:
    """The status *name* (one of _CANONICAL_STAGE_NAMES) effectively has in
    this run, whether or not it produced a StageResult at all.

    A stage absent from result.stages means one of two different things,
    now distinguished (dev-docs/TRACEABILITY_AUDIT.md, Finding #5b):

    - It was never part of this run's Flow at all -- no `interface:`
      section (connectivity) or no tb_sources (simulation) -- "SKIPPED",
      same as an explicit `--skip-*` flag (which *does* produce a
      StageResult, just with status "SKIPPED" -- returned as-is below,
      this only covers stages that were never even instantiated).
    - It *was* part of this run's Flow (present in configured_stage_names)
      but Flow.run() broke out early on an earlier stage's FAIL before
      ever reaching it -- "NOT_RUN": it wasn't skipped by anyone's choice,
      it simply never got a turn.
    """
    sr = result.stages.get(name)
    if sr is None:
        return "NOT_RUN" if name in configured_stage_names else "SKIPPED"
    return "PASS" if sr.status == "COMPLETED" else sr.status


def _stage_entry(
    result: RunResult,
    name: str,
    run_dir: Path,
    root: Path,
    *,
    configured_stage_names: frozenset[str],
    with_waves: bool = False,
) -> dict:
    """Build the results.json entry for one stage."""
    sr = result.stages.get(name)
    if sr is None:
        status = _effective_stage_status(result, name, configured_stage_names)
        entry: dict = {"status": status, "log": None}
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

    if name == "synthesis":
        if sr.technology is not None:
            entry["technology"] = sr.technology
        if sr.technology_version is not None:
            entry["technology_version"] = sr.technology_version

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


def _collect_warnings(result: RunResult) -> list[str]:
    """Flatten warnings from every stage (e.g. VF_TECHNOLOGY_PDK_NOT_INSTALLED
    from SynthesisStage) into a single ordered list for results.json."""
    warnings: list[str] = []
    for sr in result.stages.values():
        if sr.warnings:
            warnings.extend(sr.warnings)
    return warnings


def _write_results_json(
    config: ProjectWorkflowConfig,
    run_dir: Path,
    design: Design,
    result: RunResult,
    rtl_hash: dict[str, str],
    configured_stage_names: frozenset[str],
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
            "connectivity": _stage_entry(
                result, "connectivity", run_dir, root, configured_stage_names=configured_stage_names
            ),
            "simulation": _stage_entry(
                result, "simulation", run_dir, root,
                configured_stage_names=configured_stage_names, with_waves=True,
            ),
            "synthesis": _stage_entry(
                result, "synthesis", run_dir, root, configured_stage_names=configured_stage_names
            ),
        },
        "rtl_hash": rtl_hash,
        "warnings": [*config.config_warnings, *_collect_warnings(result)],
        "veriflow_version": __version__,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    generate_results_json(data, run_dir / "results.json")


def _needed_tools(
    config: ProjectWorkflowConfig, request: RunRequest | None = None
) -> tuple[bool, bool]:
    """Which EDA tools the *effective* pipeline will actually invoke.

    Mirrors build_project_flow's per-type inclusion logic exactly: a stage
    type listed in config.pipeline still doesn't run unless its precondition
    holds (connectivity needs config.interface, simulation needs
    config.tb_sources) -- so a synthesis-only project on the default
    pipeline (no interface, no tb_sources) must not be asked for iverilog.

    Also honors *request*'s skip_* flags (same behavior as Database Mode's
    run_tile, which factors skip_connectivity/skip_sim/skip_synth directly
    into its tool check) -- e.g. skip_synth=True must not require yosys
    even though synthesis is in the pipeline.
    """
    skip_connectivity = request.skip_connectivity if request else False
    skip_sim = request.skip_sim if request else False
    skip_synth = request.skip_synth if request else False

    need_iverilog = (
        not skip_connectivity
        and config.pipeline.has_stage("connectivity") and config.interface is not None
    ) or (
        not skip_sim
        and config.pipeline.has_stage("simulation") and bool(config.tb_sources)
    )
    need_yosys = not skip_synth and config.pipeline.has_stage("synthesis")
    return need_iverilog, need_yosys


def build_project_flow(
    config: ProjectWorkflowConfig,
) -> tuple[Design, Flow]:
    """Build the Design + Flow for config.pipeline (stage types, in order,
    each with its optional per-stage backend override).

    A stage type not present in config.pipeline.stages is simply never
    instantiated -- same effect as the pre-pipeline-config behavior where
    "no interface:" meant "no InterfaceStage" at all. connectivity still
    requires config.interface (there is no profile to check against
    otherwise); simulation still requires config.tb_sources non-empty --
    both preconditions unchanged from before this feature, just driven by
    "is this type in the pipeline" instead of unconditional inclusion.
    """
    design = Design(
        top_module=config.top_module,
        rtl_sources=config.rtl_sources,
        tb_sources=config.tb_sources,
    )

    profile = ExecutionProfile(
        connectivity_backend=(
            config.pipeline.backend_for("connectivity") or config.execution.connectivity_backend
        ),
        simulation_backend=(
            config.pipeline.backend_for("simulation") or config.execution.simulation_backend
        ),
        synthesis_backend=(
            config.pipeline.backend_for("synthesis") or config.execution.synthesis_backend
        ),
        technology_name=config.technology.name,
        require_pdk=config.technology.require_pdk,
    )

    stages = []
    for stage_cfg in config.pipeline.stages:
        if stage_cfg.type == "connectivity":
            if config.interface is None:
                continue
            stages.append(
                InterfaceStage(
                    interface_profile=get_interface_profile(config.interface.name),
                    profile=profile,
                    backend=get_connectivity_backend(profile.connectivity_backend),
                )
            )
        elif stage_cfg.type == "simulation":
            if not config.tb_sources:
                continue
            stages.append(
                SimulationStage(
                    tb_top=config.tb_top,
                    profile=profile,
                    backend=get_simulation_backend(profile.simulation_backend),
                )
            )
        elif stage_cfg.type == "synthesis":
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
        need_iverilog, need_yosys = _needed_tools(self.config, request)
        if need_iverilog or need_yosys:
            validate_tools(need_iverilog=need_iverilog, need_yosys=need_yosys)

        design, flow = build_project_flow(self.config)
        configured_stage_names = frozenset(s.name for s in flow.stages)

        if request is None:
            run_dir = self.config.runs_dir / get_next_run_id(self.config.runs_dir)
            run_dir.mkdir(parents=True, exist_ok=True)
            request = RunRequest(work_dir=run_dir)
        else:
            run_dir = request.work_dir
            run_dir.mkdir(parents=True, exist_ok=True)

        # rtl_hash is captured *before* any stage runs (dev-docs/
        # TRACEABILITY_AUDIT.md, Finding #1, Option A): computing it after
        # flow.run() meant the recorded hash reflected whatever the RTL
        # looked like once every tool had already finished, not what
        # verification actually started from. Snapshotting here narrows the
        # window from "the entire run's duration" to "the moment the run
        # began" -- it does not eliminate it (each stage still reads the
        # live file from disk independently, see Option B, documented as
        # pending in TRACEABILITY_AUDIT.md), but it's a real reduction in
        # risk for the common case (a run takes seconds to minutes; a
        # mid-run edit is much less likely than a stale hash computed after
        # the fact silently describing a state no tool ever saw).
        rtl_hash = _compute_rtl_hash(design.rtl_sources)

        result = flow.run(design, request)

        # Recompute the overall status over all three canonical stage
        # types, not just whichever ones Flow actually instantiated:
        # RunResult.from_stages() (inside flow.run()) only ever sees the
        # stages that were built into this Flow, so a type that was never
        # configured at all (no interface:, no tb_sources) is invisible to
        # it -- for a synthesis-only generic project that meant "status"
        # came out "PASS" even though connectivity/simulation never ran,
        # the same vacuous-truth gap as Finding #4, just reached from
        # "never configured" instead of "explicitly skipped". Using
        # _effective_stage_status for all three names (the same resolution
        # _stage_entry uses for the JSON display) closes that gap too.
        result.status = derive_run_status(
            _effective_stage_status(result, name, configured_stage_names)
            for name in _CANONICAL_STAGE_NAMES
        )

        _write_results_json(self.config, run_dir, design, result, rtl_hash, configured_stage_names)

        return ProjectRunResult(run_dir=run_dir, result=result, config_warnings=self.config.config_warnings)
