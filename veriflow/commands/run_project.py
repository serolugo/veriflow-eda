from __future__ import annotations

from pathlib import Path

from veriflow.workflows import ProjectRunResult, ProjectWorkflow
from veriflow.ui.output import console, print_done, print_section, print_status, print_warn

_ARTIFACT_INDENT = " " * 48


def cmd_run_project(config_path: Path | str) -> int:
    workflow = ProjectWorkflow.from_file(Path(config_path))
    pr = workflow.run()
    _print_result(pr)
    return 0 if pr.result.status == "PASS" else 1


def _print_result(pr: ProjectRunResult) -> None:
    status_tag = "[pass]PASS[/pass]" if pr.result.status == "PASS" else "[fail]FAIL[/fail]"
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
