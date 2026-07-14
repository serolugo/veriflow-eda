from __future__ import annotations

import argparse
from pathlib import Path

from veriflow.ui.output import console, print_done, print_step


def cmd_import_project(args: argparse.Namespace) -> int:
    """Implement `veriflow project import`.

    Imports the latest passing Project Mode run (or a specific --run) into
    a Database Mode database as a new tile. VeriFlowError (missing/failing
    run, interface mismatch, etc.) propagates to cli.py.
    """
    from veriflow.api import project_import

    config_path = Path(getattr(args, "config", "veriflow.yaml"))
    db_path = Path(args.db)
    run_id = getattr(args, "run_id", None)

    result = project_import(config_path, db_path, run_id=run_id)

    console.print()
    console.print(f"  [secondary]Config  [/secondary]  [id]{result['config_path']}[/id]")
    console.print(f"  [secondary]Database[/secondary]  [id]{result['db_path']}[/id]")
    console.print(f"  [secondary]Run     [/secondary]  [id]{result['run_id']}[/id]")
    console.print()

    print_step("project-import", f"Created tile -> {result['tile_id']}")
    print_step(
        "project-import",
        f"Copied RTL/TB sources into config/tile_{result['tile_number']}/src/",
    )
    print_step(
        "project-import",
        f"Wrote config/tile_{result['tile_number']}/imported_run.json",
    )

    print_done(
        f"Imported [id]{result['run_id']}[/id] as tile [id]{result['tile_id']}[/id]"
    )

    return 0
