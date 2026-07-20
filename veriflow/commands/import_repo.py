from __future__ import annotations

import argparse
import threading

from rich.progress import Progress, SpinnerColumn, TextColumn

from veriflow.ui.output import console, print_done, print_step, print_warn


def _run_with_spinner(fn, message: str, *, non_interactive: bool):
    """Run *fn* (a zero-arg callable) to completion, showing an animated
    spinner with *message* while it's in flight.

    Same thread+Progress pattern as `_run_subprocess_with_spinner`
    (veriflow/commands/pdk.py) -- clone+precheck+import together can take
    a while (network clone, then a real simulation/synthesis run), and
    without this nothing prints between the initial step line and the
    final result, indistinguishable from a hang. Adapted for a plain
    Python callable (returns a value or raises) rather than a subprocess,
    since `import_repo()` is one API call covering the whole flow, not a
    single subprocess this CLI command could wrap on its own.

    Suppressed entirely under `--non-interactive` (calls *fn* directly, no
    spinner) so CI log parsing never has to deal with Rich's cursor-control
    escape sequences.
    """
    if non_interactive:
        return fn()

    outcome: dict[str, object] = {}

    def _target() -> None:
        try:
            outcome["result"] = fn()
        except BaseException as exc:  # re-raised on the main thread below
            outcome["error"] = exc

    worker = threading.Thread(target=_target, daemon=True)
    worker.start()
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True,
    ) as progress:
        progress.add_task(message, total=None)
        while worker.is_alive():
            worker.join(timeout=0.1)

    if "error" in outcome:
        raise outcome["error"]  # type: ignore[misc]
    return outcome["result"]


def cmd_import_repo(args: argparse.Namespace) -> int:
    """Implement `veriflow db import-repo`.

    Clones --repo, runs its own `project run` as a real precheck, and
    imports the result into --db as a new tile. VeriFlowError (bad repo/
    branch, missing veriflow.yaml, failing precheck, already imported,
    interface/RTL problems, etc.) propagates to cli.py.
    """
    from veriflow.api import import_repo

    non_interactive = getattr(args, "non_interactive", False)

    console.print()
    console.print(f"  [secondary]Repo    [/secondary]  [id]{args.repo}[/id]")
    console.print(f"  [secondary]Branch  [/secondary]  [id]{args.branch}[/id]")
    console.print(f"  [secondary]Database[/secondary]  [id]{args.db}[/id]")
    console.print()
    print_step("import-repo", "Cloning, running precheck, and importing ...")

    result = _run_with_spinner(
        lambda: import_repo(
            args.repo,
            args.db,
            branch=args.branch,
            config_path=args.config,
            force=getattr(args, "force", False),
            allow_external_interface=getattr(args, "allow_external_interface", False),
        ),
        f"Cloning {args.repo} ({args.branch}) and verifying ...",
        non_interactive=non_interactive,
    )

    print_step("import-repo", f"Cloned {result['source_repo']} ({result['source_branch']})")
    print_step("import-repo", f"Precheck passed -- run {result['run_id']}")
    print_step("import-repo", f"Created tile -> {result['tile_id']}")

    for warning in result.get("warnings") or []:
        print_warn(warning)

    print_done(
        f"Imported [id]{result['source_repo']}[/id] ({result['source_branch']}) "
        f"as tile [id]{result['tile_id']}[/id]"
    )

    return 0
