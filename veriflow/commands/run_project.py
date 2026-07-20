from __future__ import annotations

from pathlib import Path

from veriflow.workflows import ProjectRunResult, ProjectWorkflow
from veriflow.ui.output import console, print_done, print_section, print_status, print_warn

_ARTIFACT_INDENT = " " * 48


def cmd_run_project(
    config_path: Path | str,
    *,
    skip_check: bool = False,
    skip_sim: bool = False,
    skip_synth: bool = False,
    only_check: bool = False,
    only_sim: bool = False,
    only_synth: bool = False,
    waves: bool = False,
    json_mode: bool = False,
) -> tuple[int, dict | None]:
    """Returns (exit_code, result_data). *result_data* is the full
    results.json content (read back from the run directory `workflow.run()`
    just wrote) when json_mode is True, matching the level of detail `db
    run`'s own --json output already provides (dev-docs/MODE_CONSISTENCY_AUDIT.md,
    Finding 3) -- None when json_mode is False, since nothing needs it then
    and reading the file back is otherwise pure overhead.

    skip_*/only_*/waves mirror `db run`'s own flags (Finding 5) -- same
    only_*-to-skip_* precedence as `DatabaseWorkflow.run_tile()`
    (workflows/database.py:154-166): an `only_*` flag wins over any
    individually-set `skip_*` flag for the *other* two stages.
    """
    if only_check:
        skip_sim = True
        skip_synth = True
    elif only_sim:
        skip_check = True
        skip_synth = True
    elif only_synth:
        skip_check = True
        skip_sim = True

    workflow = ProjectWorkflow.from_file(Path(config_path))

    # Only build an explicit RunRequest (and therefore only touch
    # workflow.config.runs_dir / compute run_dir ourselves) when a skip flag
    # actually applies -- workflow.run()'s own default (request=None) already
    # does this identically for the common no-flags case, so leaving it to
    # do so keeps that path untouched.
    request = None
    if skip_check or skip_sim or skip_synth:
        from veriflow.core.run_id import get_next_run_id
        from veriflow.framework import RunRequest

        run_dir = workflow.config.runs_dir / get_next_run_id(workflow.config.runs_dir)
        run_dir.mkdir(parents=True, exist_ok=True)
        request = RunRequest(
            work_dir=run_dir,
            skip_connectivity=skip_check,
            skip_sim=skip_sim,
            skip_synth=skip_synth,
        )
    pr = workflow.run(request)
    _print_result(pr)
    exit_code = 0 if pr.result.status == "PASS" else 1

    if waves:
        _maybe_launch_waves(pr)

    result_data: dict | None = None
    if json_mode:
        from veriflow.api import get_project_run_result

        result_data = get_project_run_result(pr.run_dir)

    return exit_code, result_data


def _maybe_launch_waves(pr: ProjectRunResult) -> None:
    """Open the waveform viewer for this run's simulation stage, if it ran
    and produced a wave file -- same convention as `db run --waves`
    (commands/run.py), ported here since Project Mode's SimulationStage
    already records a wave artifact but had no CLI flag to open it
    (dev-docs/MODE_CONSISTENCY_AUDIT.md, Finding 5/8). A no-op if
    simulation was skipped or produced no wave file (e.g. no tb_sources)."""
    from veriflow.core.sim_runner import launch_waves

    sr = pr.result.stages.get("simulation")
    if sr is None or not sr.artifacts or not sr.artifacts.get("wave"):
        return
    wave_path = pr.run_dir / sr.artifacts["wave"][0]
    if wave_path.exists():
        launch_waves(wave_path)


_STATUS_TAGS = {
    "PASS": "[pass]PASS[/pass]",
    "PARTIAL": "[warn]PARTIAL[/warn]",
}


def _print_result(pr: ProjectRunResult) -> None:
    status_tag = _STATUS_TAGS.get(pr.result.status, "[fail]FAIL[/fail]")
    console.print()
    console.print(f"  [secondary]Project run[/secondary]  [id]{pr.run_dir}[/id]")
    console.print(f"  [secondary]Status     [/secondary]  {status_tag}")
    console.print(f"  [secondary]-> results: {pr.run_dir / 'results.json'}[/secondary]")

    for warning in pr.config_warnings:
        print_warn(warning)
    for sr in pr.result.stages.values():
        for warning in sr.warnings or []:
            print_warn(warning)

    print_section("Stages")
    for stage_name, sr in pr.result.stages.items():
        first_log = sr.log_paths[0] if sr.log_paths else ""
        print_status(stage_name, sr.status, first_log)

        extra: list[str] = list(sr.log_paths[1:]) if sr.log_paths else []
        if sr.artifacts:
            for paths in sr.artifacts.values():
                extra += [p for p in (paths if isinstance(paths, list) else [paths]) if p]

        for p in extra:
            console.print(f"  [secondary]{_ARTIFACT_INDENT}{p}[/secondary]")

    print_done(
        f"Project run complete  ·  [id]{pr.run_dir.name}[/id]  ·  status: {pr.result.status}"
    )
