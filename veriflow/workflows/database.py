from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import yaml

from veriflow.core import VeriFlowError
from veriflow.core.backends.registry import (
    get_connectivity_tool_name,
    get_simulation_tool_name,
    get_synthesis_tool_name,
)
from veriflow.core.copier import copy_flat
from veriflow.core.csv_store import append_record, get_tile_row, read_tile_index
from veriflow.core.pipeline import PipelineRunner
from veriflow.core.pipeline_builder import build_default_pipeline
from veriflow.core.run_id import get_next_run_id
from veriflow.core.validator import (
    detect_iverilog_version,
    validate_database,
    validate_run_inputs,
    validate_tools,
)
from veriflow.framework.status import derive_run_status
from veriflow.generators.manifest import generate_manifest
from veriflow.generators.notes import generate_notes
from veriflow.generators.readme import generate_readme
from veriflow.generators.results import generate_results_json
from veriflow.generators.summary import generate_summary
from veriflow.models.execution_profile import ExecutionProfile, default_execution_profile
from veriflow.models.interface_profile import get_interface_profile, list_interface_profile_names
from veriflow.models.pipeline_config import DEFAULT_PIPELINE
from veriflow.models.project_config import ProjectConfig
from veriflow.models.run_context import RunContext
from veriflow.models.stage_result import StageResult
from veriflow.models.tile_config import TileConfig


@dataclass
class DatabaseRunOptions:
    skip_connectivity: bool = False
    skip_sim: bool = False
    skip_synth: bool = False
    only_connectivity: bool = False
    only_sim: bool = False
    only_synth: bool = False


@dataclass
class DatabaseRunResult:
    tile_id: str
    run_id: str
    run_dir: Path
    status: str
    interface_name: str | None
    stages: dict[str, StageResult]
    sources: dict[str, list[Path]]
    artifacts: dict[str, object]
    data: dict

    def to_dict(self) -> dict:
        return self.data


@dataclass
class DatabaseTileInfo:
    tile_number: str
    tile_id: str
    tile_name: str
    tile_author: str
    version: str | None = None
    revision: str | None = None
    interface_name: str | None = None


@dataclass
class DatabaseRunInfo:
    tile_id: str
    run_id: str
    run_dir: Path
    status: str | None = None
    date: str | None = None
    objective: str | None = None
    summary: str | None = None
    results_path: Path | None = None
    wave_path: Path | None = None


_RUN_DIR_PATTERN = re.compile(r"^run-(\d{3})$")


def _normalize_run_id(run_id: str) -> str:
    """Accept a bare run number (e.g. "8") and normalize it to "run-008",
    mirroring how --tile 1 resolves to tile_0001. Already-formatted ids
    (e.g. "run-008") pass through unchanged."""
    if run_id.isdigit():
        return f"run-{int(run_id):03d}"
    return run_id


_TB_DUT_INSTANCE_RE = re.compile(r"(\w+)\s+DUT\s*\(")


def _check_tb_module_mismatch(tb_files: list[Path], top_module: str) -> str | None:
    """Warn when tb_tile.v instantiates a module name that no longer matches
    tile_config.yaml's top_module (e.g. after switching RTL to a wrapper).

    tb_tile.v is self-contained and hand-edited by the user, so this is a
    warning, not an error: a mismatch may be intentional.
    """
    if not top_module:
        return None
    tb_tile = next((f for f in tb_files if f.name == "tb_tile.v"), None)
    if tb_tile is None:
        return None
    try:
        content = tb_tile.read_text(encoding="utf-8")
    except OSError:
        return None
    if re.search(rf"\b{re.escape(top_module)}\s+\w+\s*\(", content):
        return None
    match = _TB_DUT_INSTANCE_RE.search(content)
    if match is None:
        return None
    found_module = match.group(1)
    if found_module == top_module:
        return None
    return (
        f"tb_tile.v instantiates '{found_module}' but tile_config.yaml declares "
        f"top_module as '{top_module}' -- update tb_tile.v if needed"
    )


class DatabaseWorkflow:
    def __init__(self, database_path: Path | str) -> None:
        self.db_path = Path(database_path)

    def run_tile(
        self,
        tile_number: str,
        options: DatabaseRunOptions | None = None,
    ) -> DatabaseRunResult:
        """Execute the full verification pipeline for one tile.

        No Rich terminal output or waveform viewer is launched here;
        those are the caller's responsibility.
        """
        if options is None:
            options = DatabaseRunOptions()

        # Resolve skip flags from only_* flags
        skip_check = options.skip_connectivity
        skip_sim = options.skip_sim
        skip_synth = options.skip_synth
        if options.only_connectivity:
            skip_sim = True
            skip_synth = True
        elif options.only_sim:
            skip_check = True
            skip_synth = True
        elif options.only_synth:
            skip_check = True
            skip_sim = True

        # ── 1. Validate database ──────────────────────────────────────────────
        validate_database(self.db_path)

        tile_number_str = f"{int(tile_number):04d}"

        # ── 2. Read configs ───────────────────────────────────────────────────
        config_tile_dir = self.db_path / "config" / f"tile_{tile_number_str}"
        if not config_tile_dir.exists():
            raise VeriFlowError(f"Config directory not found: {config_tile_dir}")

        tile_cfg_path = config_tile_dir / "tile_config.yaml"
        if not tile_cfg_path.exists():
            raise VeriFlowError(
                f"tile_config.yaml not found: {tile_cfg_path}",
                code="VF_TILE_CONFIG_MISSING",
                details={"path": str(tile_cfg_path)},
            )

        try:
            tile_config = TileConfig.from_dict(
                yaml.safe_load(tile_cfg_path.read_text(encoding="utf-8")) or {}
            )
        except yaml.YAMLError as exc:
            raise VeriFlowError(
                f"YAML parse error in {tile_cfg_path}:\n  {exc}",
                code="VF_TILE_CONFIG_YAML_ERROR",
                details={"path": str(tile_cfg_path)},
            ) from exc

        project_cfg_path = self.db_path / "project_config.yaml"
        try:
            project_config = ProjectConfig.from_dict(
                yaml.safe_load(project_cfg_path.read_text(encoding="utf-8")) or {},
                root=self.db_path,
            )
        except yaml.YAMLError as exc:
            raise VeriFlowError(
                f"YAML parse error in {project_cfg_path}:\n  {exc}",
                code="VF_DATABASE_CONFIG_YAML_ERROR",
                details={"path": str(project_cfg_path)},
            ) from exc
        interface_name = project_config.interface_name
        interface_profile = get_interface_profile(interface_name)

        if options.only_connectivity and interface_profile is None:
            profiles = ", ".join(repr(p) for p in list_interface_profile_names())
            raise VeriFlowError(
                "Cannot run connectivity check (--only-check): no interface profile is configured.\n"
                "  Set 'interface_name' in project_config.yaml to enable interface checking.\n"
                f"  Registered profiles: {profiles}",
                code="VF_INTERFACE_CHECK_NO_PROFILE",
            )

        # Projects with no interface profile skip connectivity automatically
        if interface_profile is None:
            skip_check = True

        # ── Resolve effective pipeline: tile_config > project_config > default ─
        # A stage type absent from the effective pipeline behaves exactly like
        # the matching --skip-* flag -- same StageResult(status="SKIPPED"),
        # no restructuring of build_default_pipeline needed. Per-stage
        # `backend:` overrides feed a custom ExecutionProfile.
        effective_pipeline = tile_config.pipeline or project_config.pipeline or DEFAULT_PIPELINE
        if not effective_pipeline.has_stage("connectivity"):
            skip_check = True
        if not effective_pipeline.has_stage("simulation"):
            skip_sim = True
        if not effective_pipeline.has_stage("synthesis"):
            skip_synth = True

        # require_pdk: tile_config.yaml's own technology.require_pdk (if set)
        # overrides project_config.yaml's database-wide default -- same
        # tile > project > default precedence as effective_pipeline above.
        effective_require_pdk = (
            tile_config.require_pdk if tile_config.require_pdk is not None else project_config.require_pdk
        )

        _exec_defaults = default_execution_profile()
        pipeline_profile = ExecutionProfile(
            connectivity_backend=(
                effective_pipeline.backend_for("connectivity") or _exec_defaults.connectivity_backend
            ),
            simulation_backend=(
                effective_pipeline.backend_for("simulation") or _exec_defaults.simulation_backend
            ),
            synthesis_backend=(
                effective_pipeline.backend_for("synthesis") or _exec_defaults.synthesis_backend
            ),
            technology_name=project_config.technology_name or _exec_defaults.technology_name,
            require_pdk=effective_require_pdk,
        )

        # Validate only the tools needed by the stages that will actually run.
        # iverilog: connectivity + simulation; yosys: synthesis only.
        need_iverilog = not (skip_check and skip_sim)
        need_yosys = not skip_synth
        if need_iverilog or need_yosys:
            validate_tools(need_iverilog=need_iverilog, need_yosys=need_yosys)

        validate_run_inputs(self.db_path, tile_number_str, tile_config)

        # ── 3. Look up tile_id and sync tile_name/tile_author ─────────────────
        tile_index_path = self.db_path / "tile_index.csv"
        tile_row = get_tile_row(tile_index_path, tile_number_str)
        tile_id = tile_row["tile_id"]
        id_version = tile_row["version"]
        id_revision = tile_row["revision"]

        if tile_config.tile_name or tile_config.tile_author:
            from veriflow.core.csv_store import update_tile_index
            updated_row = dict(tile_row)
            updated_row["tile_name"] = tile_config.tile_name
            updated_row["tile_author"] = tile_config.tile_author
            update_tile_index(tile_index_path, tile_number_str, updated_row)

        tile_dir = self.db_path / "tiles" / tile_id
        runs_dir = tile_dir / "runs"

        # ── 4. Determine next run ID ──────────────────────────────────────────
        run_id = get_next_run_id(runs_dir)
        today_str = date.today().isoformat()

        ctx = RunContext(
            db_path=self.db_path,
            tile_id=tile_id,
            run_id=run_id,
            tile_dir=tile_dir,
            run_dir=runs_dir / run_id,
            interface_name=interface_name,
            skip_connectivity=skip_check,
            skip_sim=skip_sim,
            skip_synth=skip_synth,
        )

        # ── 5. Create run folder structure ────────────────────────────────────
        run_dir = ctx.run_dir
        for sub in (
            "src/rtl", "src/tb",
            "out/connectivity/logs",
            "out/sim/logs", "out/sim/waves",
            "out/synth/logs", "out/synth/reports",
        ):
            _gitkeep(run_dir / sub)

        # ── 6. Copy RTL sources to run/src/rtl/ ───────────────────────────────
        src_rtl = config_tile_dir / "src" / "rtl"
        dst_rtl = run_dir / "src" / "rtl"
        rtl_files = copy_flat(src_rtl, dst_rtl)

        # ── 7. Copy TB sources (if present) ───────────────────────────────────
        src_tb = config_tile_dir / "src" / "tb"
        dst_tb = run_dir / "src" / "tb"
        tb_files: list[Path] = []
        has_tb = src_tb.exists() and any(src_tb.glob("*.v"))
        if has_tb:
            tb_files = copy_flat(src_tb, dst_tb)
        else:
            skip_sim = True
            # Rebuild ctx so skip_sim propagates into stage execution
            ctx = RunContext(
                db_path=self.db_path,
                tile_id=tile_id,
                run_id=run_id,
                tile_dir=tile_dir,
                run_dir=runs_dir / run_id,
                interface_name=interface_name,
                skip_connectivity=skip_check,
                skip_sim=True,
                skip_synth=skip_synth,
            )

        # ── 8. Detect tool version ────────────────────────────────────────────
        iverilog_version = detect_iverilog_version()

        # ── Non-fatal: tb_tile.v vs tile_config.yaml top_module sync check ────
        # Seeded with both config layers' own config-parse-time warnings
        # (interface_definition name mismatch/profile-overwrite, unknown
        # top-level keys) -- same "surfaced in results, not a raw Python
        # UserWarning" treatment as Project Mode's ProjectWorkflowConfig
        # .config_warnings.
        warnings: list[str] = list(project_config.config_warnings) + list(tile_config.config_warnings)
        tb_mismatch = _check_tb_module_mismatch(tb_files, tile_config.top_module)
        if tb_mismatch:
            warnings.append(tb_mismatch)

        # ── 9. Build pipeline stages ──────────────────────────────────────────
        pipeline = build_default_pipeline(
            rtl_files=rtl_files,
            tb_files=tb_files,
            tb_top=tile_config.tb_top_module,
            top_module=tile_config.top_module,
            interface_profile=interface_profile,
            profile=pipeline_profile,
        )
        conn_stage, sim_stage, synth_stage = pipeline.stages

        # ── 10. Accumulators and log paths ────────────────────────────────────
        conn_result = "SKIPPED"
        sim_result = "SKIPPED"
        synth_result = "SKIPPED"
        sim_parsed: dict = {"sim_time": "", "seed": ""}
        synth_parsed: dict = {"cells": "", "warnings": "0", "errors": "0", "has_latches": False}

        conn_log_path = ctx.impl_dir / "logs" / "connectivity.log"
        sim_log_path = ctx.sim_dir / "logs" / "sim.log"
        wave_path = ctx.sim_dir / "waves" / "waves.vcd"
        synth_log_path = ctx.synth_dir / "logs" / "synth.log"

        # ── 11. Connectivity check ────────────────────────────────────────────
        _conn_sr = PipelineRunner([conn_stage], design=pipeline.design).run(ctx)["connectivity"]
        conn_result = _conn_sr.status

        if not skip_check and conn_result == "FAIL":
            data = _finalize_run(
                ctx=ctx, today_str=today_str,
                tile_config=tile_config,
                id_version=id_version, id_revision=id_revision,
                rtl_files=rtl_files, tb_files=tb_files,
                conn_result=conn_result, sim_result=sim_result, synth_result=synth_result,
                sim_parsed=sim_parsed, synth_parsed=synth_parsed,
                iverilog_version=iverilog_version,
                conn_log_path=conn_log_path, sim_log_path=sim_log_path,
                synth_log_path=synth_log_path, wave_path=wave_path,
                profile=pipeline_profile,
                warnings=warnings,
            )
            return DatabaseRunResult(
                tile_id=tile_id,
                run_id=run_id,
                run_dir=run_dir,
                status=data["status"],
                interface_name=interface_name,
                stages={
                    "connectivity": _conn_sr,
                    "simulation": StageResult(name="simulation", status="SKIPPED"),
                    "synthesis": StageResult(name="synthesis", status="SKIPPED"),
                },
                sources={"rtl": rtl_files, "tb": tb_files},
                artifacts=data.get("artifacts", {}),
                data=data,
            )

        # ── 12. Simulation ────────────────────────────────────────────────────
        _sim_sr = PipelineRunner([sim_stage], design=pipeline.design).run(ctx)["simulation"]
        sim_result = _sim_sr.status
        sim_parsed = dict(_sim_sr.metrics) if _sim_sr.metrics else {"sim_time": "", "seed": ""}

        # ── 13. Synthesis ─────────────────────────────────────────────────────
        _synth_sr = PipelineRunner([synth_stage], design=pipeline.design).run(ctx)["synthesis"]
        synth_result = _synth_sr.status
        synth_parsed = (
            dict(_synth_sr.metrics)
            if _synth_sr.metrics
            else {"cells": "", "warnings": "0", "errors": "0", "has_latches": False}
        )
        if _synth_sr.warnings:
            warnings.extend(_synth_sr.warnings)

        # ── 14. Finalize ──────────────────────────────────────────────────────
        data = _finalize_run(
            ctx=ctx, today_str=today_str,
            tile_config=tile_config,
            id_version=id_version, id_revision=id_revision,
            rtl_files=rtl_files, tb_files=tb_files,
            conn_result=conn_result, sim_result=sim_result, synth_result=synth_result,
            sim_parsed=sim_parsed, synth_parsed=synth_parsed,
            iverilog_version=iverilog_version,
            conn_log_path=conn_log_path, sim_log_path=sim_log_path,
            synth_log_path=synth_log_path, wave_path=wave_path,
            profile=pipeline_profile,
            warnings=warnings,
            synth_technology=_synth_sr.technology,
            synth_technology_version=_synth_sr.technology_version,
        )

        return DatabaseRunResult(
            tile_id=tile_id,
            run_id=run_id,
            run_dir=run_dir,
            status=data["status"],
            interface_name=interface_name,
            stages={
                "connectivity": _conn_sr,
                "simulation": _sim_sr,
                "synthesis": _synth_sr,
            },
            sources={"rtl": rtl_files, "tb": tb_files},
            artifacts=data.get("artifacts", {}),
            data=data,
        )

    # ── Read-only APIs ────────────────────────────────────────────────────────

    def list_tiles(self) -> list[DatabaseTileInfo]:
        """Return one DatabaseTileInfo per registered tile, sorted by tile_number."""
        tile_index_path = self.db_path / "tile_index.csv"
        if not tile_index_path.exists():
            return []
        rows = read_tile_index(tile_index_path)
        tiles: list[DatabaseTileInfo] = []
        for row in rows:
            tiles.append(DatabaseTileInfo(
                tile_number=row["tile_number"],
                tile_id=row["tile_id"],
                tile_name=row.get("tile_name", ""),
                tile_author=row.get("tile_author", ""),
                version=row.get("version") or None,
                revision=row.get("revision") or None,
                interface_name=row.get("interface_name") or None,
            ))
        tiles.sort(key=lambda t: int(t.tile_number))
        return tiles

    def list_runs(
        self,
        tile_id: str | None = None,
        tile_number: str | None = None,
    ) -> list[DatabaseRunInfo]:
        """Return all runs for a tile, sorted by run number.

        Caller must supply tile_id or tile_number.  If tile_number is given it
        is resolved through tile_index.csv.  Missing results.json is tolerated;
        status will be None for those runs.
        """
        resolved_id = self._resolve_tile_id(tile_id, tile_number)
        tile_dir = self.db_path / "tiles" / resolved_id
        if not tile_dir.exists():
            raise VeriFlowError(
                f"Tile directory not found: {tile_dir}",
                code="VF_DATABASE_TILE_NOT_FOUND",
                details={"tile_id": resolved_id},
            )
        runs_dir = tile_dir / "runs"
        if not runs_dir.exists():
            return []
        run_entries: list[tuple[int, Path]] = []
        for entry in runs_dir.iterdir():
            if entry.is_dir():
                m = _RUN_DIR_PATTERN.match(entry.name)
                if m:
                    run_entries.append((int(m.group(1)), entry))
        run_entries.sort(key=lambda x: x[0])
        return [_load_run_info(resolved_id, run_dir) for _, run_dir in run_entries]

    def load_run_result(
        self,
        *,
        tile_id: str | None = None,
        tile_number: str | None = None,
        run_id: str,
    ) -> DatabaseRunResult:
        """Load a persisted DatabaseRunResult from results.json without re-executing tools.

        Raises VF_DATABASE_RUN_RESULT_MISSING when results.json is absent.
        Stages are reconstructed from the persisted stage dictionary.
        """
        run_id = _normalize_run_id(run_id)
        resolved_id = self._resolve_tile_id(tile_id, tile_number)
        tile_dir = self.db_path / "tiles" / resolved_id
        if not tile_dir.exists():
            raise VeriFlowError(
                f"Tile directory not found: {tile_dir}",
                code="VF_DATABASE_TILE_NOT_FOUND",
                details={"tile_id": resolved_id},
            )
        run_dir = tile_dir / "runs" / run_id
        if not run_dir.exists():
            raise VeriFlowError(
                f"Run directory not found: {run_dir}",
                code="VF_DATABASE_RUN_NOT_FOUND",
                details={"tile_id": resolved_id, "run_id": run_id},
            )
        results_path = run_dir / "results.json"
        if not results_path.exists():
            raise VeriFlowError(
                f"results.json missing for run {run_id!r} of tile {resolved_id!r}",
                code="VF_DATABASE_RUN_RESULT_MISSING",
                details={"tile_id": resolved_id, "run_id": run_id, "path": str(results_path)},
            )
        data = json.loads(results_path.read_text(encoding="utf-8"))
        stages = {
            name: _stage_result_from_dict(name, sd)
            for name, sd in data.get("stages", {}).items()
        }
        return DatabaseRunResult(
            tile_id=data.get("tile_id", resolved_id),
            run_id=data.get("run_id", run_id),
            run_dir=run_dir,
            status=data.get("status", ""),
            interface_name=data.get("interface_name"),
            stages=stages,
            sources=data.get("sources", {}),
            artifacts=data.get("artifacts", {}),
            data=data,
        )

    def _resolve_tile_id(self, tile_id: str | None, tile_number: str | None) -> str:
        if tile_id is not None:
            return tile_id
        if tile_number is not None:
            tile_number_str = f"{int(tile_number):04d}"
            row = get_tile_row(self.db_path / "tile_index.csv", tile_number_str)
            return row["tile_id"]
        raise VeriFlowError(
            "Must provide either tile_id or tile_number",
            code="VF_DATABASE_MISSING_TILE_IDENTIFIER",
        )


# ── Private helpers ───────────────────────────────────────────────────────────

def _gitkeep(d: Path) -> None:
    d.mkdir(parents=True, exist_ok=True)
    (d / ".gitkeep").touch()


def _derive_status(conn: str, sim: str, synth: str) -> str:
    """Thin wrapper kept for call-site readability -- the actual aggregation
    logic lives in veriflow.framework.status.derive_run_status, shared with
    Project Mode (dev-docs/TRACEABILITY_AUDIT.md, Findings #4/#4b)."""
    return derive_run_status([conn, sim, synth])


def _load_run_info(tile_id: str, run_dir: Path) -> DatabaseRunInfo:
    """Build a DatabaseRunInfo by reading persisted files; never writes."""
    run_id = run_dir.name
    results_path = run_dir / "results.json"
    wave_path = run_dir / "out" / "sim" / "waves" / "waves.vcd"

    status: str | None = None
    run_date: str | None = None
    objective: str | None = None

    if results_path.exists():
        try:
            rdata = json.loads(results_path.read_text(encoding="utf-8"))
            status = rdata.get("status")
            run_date = rdata.get("date")
        except Exception:
            pass

    manifest_path = run_dir / "manifest.yaml"
    if manifest_path.exists():
        try:
            manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
            objective = manifest.get("objective")
        except Exception:
            pass

    return DatabaseRunInfo(
        tile_id=tile_id,
        run_id=run_id,
        run_dir=run_dir,
        status=status,
        date=run_date,
        objective=objective,
        summary=None,
        results_path=results_path if results_path.exists() else None,
        wave_path=wave_path if wave_path.exists() else None,
    )


def _stage_result_from_dict(name: str, d: dict) -> StageResult:
    """Reconstruct a StageResult from a persisted stage dictionary."""
    return StageResult(
        name=name,
        status=d.get("status", "SKIPPED"),
        tool=d.get("tool"),
        log_paths=d.get("logs"),
        artifacts=d.get("artifacts"),
        metrics=d.get("metrics"),
        error=d.get("error"),
    )


def _finalize_run(
    ctx: RunContext,
    today_str: str,
    tile_config: TileConfig,
    id_version: str,
    id_revision: str,
    rtl_files: list[Path],
    tb_files: list[Path],
    conn_result: str,
    sim_result: str,
    synth_result: str,
    sim_parsed: dict,
    synth_parsed: dict,
    iverilog_version: str,
    conn_log_path: Path,
    sim_log_path: Path,
    synth_log_path: Path,
    wave_path: Path,
    profile: ExecutionProfile,
    warnings: list[str] | None = None,
    synth_technology: str | None = None,
    synth_technology_version: str | None = None,
) -> dict:
    """Generate all documentation, update CSV, and return the run_result dict."""

    tiles_dir = ctx.db_path / "tiles"

    def rel(p: Path) -> str:
        try:
            return "tiles/" + p.relative_to(tiles_dir).as_posix()
        except ValueError:
            return p.as_posix()

    status = _derive_status(conn_result, sim_result, synth_result)

    conn_logs = [rel(conn_log_path)] if conn_log_path.exists() else []
    sim_logs = [rel(sim_log_path)] if sim_log_path.exists() else []
    synth_logs = [rel(synth_log_path)] if synth_log_path.exists() else []
    wave_files = [rel(wave_path)] if wave_path.exists() else []

    # ── Generate manifest.yaml ────────────────────────────────────────────────
    manifest_data = {
        "tile_id": ctx.tile_id,
        "run_id": ctx.run_id,
        "date": today_str,
        "author": tile_config.run_author,
        "objective": tile_config.objective,
        "status": status,
        "tile": {
            "tile_name": tile_config.tile_name,
            "top_module": tile_config.top_module,
            "version": id_version,
            "revision": id_revision,
        },
        "tools": {
            "simulator": get_simulation_tool_name(profile.simulation_backend),
            "simulator_version": iverilog_version,
            "synthesizer": get_synthesis_tool_name(profile.synthesis_backend),
            "synthesizer_version": "",
        },
        "run": {
            "sim_time": sim_parsed.get("sim_time", ""),
            "seed": sim_parsed.get("seed", ""),
        },
        "sources": {
            "rtl": [rel(f) for f in rtl_files],
            "tb": [rel(f) for f in tb_files],
        },
        "artifacts": {
            "connectivity_log": conn_logs,
            "sim_log": sim_logs,
            "synth_log": synth_logs,
            "wave": wave_files,
        },
        "results": {
            "connectivity": conn_result,
            "simulation": sim_result,
            "synthesis": synth_result,
            "cells": synth_parsed.get("cells", ""),
            "warnings": synth_parsed.get("warnings", ""),
            "errors": synth_parsed.get("errors", ""),
        },
    }
    generate_manifest(manifest_data, ctx.manifest_path)

    # ── Generate notes.md ─────────────────────────────────────────────────────
    generate_notes(ctx.tile_id, tile_config, ctx.notes_path)

    # ── Regenerate README.md ──────────────────────────────────────────────────
    generate_readme(ctx.tile_id, tile_config, ctx.tile_dir / "README.md")

    # ── Update works/ ─────────────────────────────────────────────────────────
    works_rtl = ctx.tile_dir / "works" / "rtl"
    works_tb = ctx.tile_dir / "works" / "tb"
    for f in works_rtl.glob("*.v"):
        f.unlink()
    for f in works_tb.glob("*.v"):
        f.unlink()
    copy_flat(ctx.src_dir / "rtl", works_rtl)
    if (ctx.src_dir / "tb").exists():
        copy_flat(ctx.src_dir / "tb", works_tb)

    # ── Append row to records.csv ─────────────────────────────────────────────
    run_path_rel = rel(ctx.run_dir)
    records_csv = ctx.db_path / "records.csv"
    append_record(records_csv, {
        "Tile_ID": ctx.tile_id,
        "Run_ID": ctx.run_id,
        "Date": today_str,
        "Author": tile_config.run_author,
        "Objective": tile_config.objective,
        "Status": status,
        "Version": id_version,
        "Revision": id_revision,
        "Connectivity": conn_result,
        "Simulation": sim_result,
        "Synthesis": synth_result,
        "Tool_Version": iverilog_version,
        "Main_Change": tile_config.main_change,
        "Run_Path": run_path_rel,
        "Tags": tile_config.tags,
        "Interface": ctx.interface_name or "",
    })

    # ── Generate summary.md ───────────────────────────────────────────────────
    generate_summary(
        tile_id=ctx.tile_id,
        tile_name=tile_config.tile_name,
        run_id=ctx.run_id,
        date=today_str,
        connectivity=conn_result,
        simulation=sim_result,
        synthesis=synth_result,
        cells=synth_parsed.get("cells", ""),
        warnings=synth_parsed.get("warnings", "0"),
        errors=synth_parsed.get("errors", "0"),
        sim_time=sim_parsed.get("sim_time", ""),
        precheck_status=conn_result,
        output_path=ctx.summary_path,
    )

    # ── Generate results.json ─────────────────────────────────────────────────
    readme_path = ctx.tile_dir / "README.md"

    sim_metrics: dict = {}
    if sim_parsed.get("sim_time"):
        sim_metrics["sim_time"] = sim_parsed["sim_time"]
    if sim_parsed.get("seed"):
        sim_metrics["seed"] = sim_parsed["seed"]
    synth_metrics: dict = {
        "cells": synth_parsed.get("cells", ""),
        "warnings": synth_parsed.get("warnings", "0"),
        "errors": synth_parsed.get("errors", "0"),
        "has_latches": synth_parsed.get("has_latches", False),
    }

    run_result: dict = {
        "schema_version": "1.2",
        "tile_id": ctx.tile_id,
        "run_id": ctx.run_id,
        "date": today_str,
        "status": status,
        "interface_name": ctx.interface_name,
        "stages": {
            "connectivity": StageResult(
                name="connectivity",
                status=conn_result,
                tool=get_connectivity_tool_name(profile.connectivity_backend),
                log_paths=conn_logs or None,
            ).to_dict(),
            "simulation": StageResult(
                name="simulation",
                status=sim_result,
                tool=get_simulation_tool_name(profile.simulation_backend),
                log_paths=sim_logs or None,
                artifacts={"wave": wave_files} if wave_files else None,
                metrics=sim_metrics or None,
            ).to_dict(),
            "synthesis": StageResult(
                name="synthesis",
                status=synth_result,
                tool=get_synthesis_tool_name(profile.synthesis_backend),
                log_paths=synth_logs or None,
                metrics=synth_metrics,
                technology=synth_technology,
                technology_version=synth_technology_version,
            ).to_dict(),
        },
        "sources": {
            "rtl": [rel(f) for f in rtl_files],
            "tb": [rel(f) for f in tb_files],
        },
        "artifacts": {
            "manifest": [rel(ctx.manifest_path)],
            "summary": [rel(ctx.summary_path)],
            "notes": [rel(ctx.notes_path)],
            "readme": [rel(readme_path)] if readme_path.exists() else [],
            "records": [records_csv.relative_to(ctx.db_path).as_posix()] if records_csv.exists() else [],
            "connectivity_log": conn_logs,
            "sim_log": sim_logs,
            "synth_log": synth_logs,
            "wave": wave_files,
        },
        "warnings": warnings or [],
        "error": None,
    }
    generate_results_json(run_result, ctx.results_path)

    return run_result
