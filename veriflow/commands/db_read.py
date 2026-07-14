"""
veriflow.commands.db_read
--------------------------
Read-only Database Mode commands backed by DatabaseWorkflow read APIs.

These handlers never call run_tile(), never write files, and never append CSVs.
"""

from __future__ import annotations

from pathlib import Path

from veriflow.ui.output import (
    console,
    print_runs_table,
    print_section,
    print_tiles_table,
    print_title,
)
from veriflow.workflows.database import (
    DatabaseRunInfo,
    DatabaseRunResult,
    DatabaseTileInfo,
    DatabaseWorkflow,
)


def cmd_db_list_tiles(db: Path | str) -> list[DatabaseTileInfo]:
    """List all registered tiles in the database."""
    wf = DatabaseWorkflow(db)
    tiles = wf.list_tiles()

    print_title("Tiles")
    if not tiles:
        console.print("  [secondary](no tiles registered)[/secondary]")
        return tiles

    rows = []
    for t in tiles:
        v = f"v{t.version}" if t.version else "v?"
        r = f"r{t.revision}" if t.revision else "r?"
        rows.append((
            t.tile_number,
            t.tile_id,
            t.tile_name or "—",
            t.tile_author or "—",
            f"{v} {r}",
            t.interface_name or "—",
        ))
    print_tiles_table(rows)

    return tiles


def cmd_db_list_runs(
    db: Path | str,
    tile: str | None = None,
    tile_id: str | None = None,
) -> list[DatabaseRunInfo]:
    """List all runs for a tile."""
    wf = DatabaseWorkflow(db)
    runs = wf.list_runs(tile_id=tile_id, tile_number=tile)

    if runs:
        display_id = runs[0].tile_id
    elif tile_id:
        display_id = tile_id
    elif tile:
        display_id = f"tile_{int(tile):04d}"
    else:
        display_id = "?"

    print_title(f"Runs for {display_id}")
    if not runs:
        console.print("  [secondary](no runs found)[/secondary]")
        return runs

    rows = []
    for r in runs:
        status_markup = _status_markup(r.status)
        date_str = r.date or "—"
        wave_markup = "[pass]yes[/pass]" if r.wave_path else "[secondary]no[/secondary]"
        rows.append((r.run_id, status_markup, date_str, wave_markup))
    print_runs_table(rows)

    return runs


def cmd_db_show_run(
    db: Path | str,
    run_id: str,
    tile: str | None = None,
    tile_id: str | None = None,
) -> DatabaseRunResult:
    """Show detailed information for a specific run."""
    wf = DatabaseWorkflow(db)
    result = wf.load_run_result(tile_id=tile_id, tile_number=tile, run_id=run_id)

    print_section(f"Run {result.run_id}")
    console.print(f"  [secondary]Status:   [/secondary] {_status_markup(result.status)}")
    console.print(f"  [secondary]Tile:     [/secondary] [id]{result.tile_id}[/id]")
    console.print(f"  [secondary]Interface:[/secondary] {result.interface_name or '—'}")
    console.print()
    console.print("  [label]Stages:[/label]")

    for stage_name, stage_result in result.stages.items():
        status_markup = _status_markup(stage_result.status)
        log_paths = stage_result.log_paths or []
        wave_files: list[str] = []
        if stage_result.artifacts:
            for art_val in stage_result.artifacts.values():
                if isinstance(art_val, list):
                    wave_files.extend(str(v) for v in art_val)
        all_files = list(log_paths) + wave_files

        if all_files:
            console.print(
                f"    [secondary]{stage_name:<14}[/secondary] {status_markup}"
                f"  [secondary]{all_files[0]}[/secondary]"
            )
            for f in all_files[1:]:
                console.print(f"    {'':14}          [secondary]{f}[/secondary]")
        else:
            console.print(f"    [secondary]{stage_name:<14}[/secondary] {status_markup}")

    return result


# ── JSON serialization helpers ────────────────────────────────────────────────

def tile_info_to_dict(t: DatabaseTileInfo) -> dict:
    return {
        "tile_number": t.tile_number,
        "tile_id": t.tile_id,
        "tile_name": t.tile_name,
        "tile_author": t.tile_author,
        "version": t.version,
        "revision": t.revision,
        "interface_name": t.interface_name,
    }


def run_info_to_dict(r: DatabaseRunInfo) -> dict:
    return {
        "tile_id": r.tile_id,
        "run_id": r.run_id,
        "status": r.status,
        "date": r.date,
        "objective": r.objective,
        "wave_available": r.wave_path is not None,
    }


# ── Private helpers ───────────────────────────────────────────────────────────

def _status_markup(status: str | None) -> str:
    if status == "PASS":
        return "[pass]PASS[/pass]"
    if status == "FAIL":
        return "[fail]FAIL[/fail]"
    if status == "PARTIAL":
        return "[warn]PARTIAL[/warn]"
    if status in ("SKIPPED", "SKIP"):
        return "[secondary]SKIPPED[/secondary]"
    if status == "COMPLETED":
        # Simulation stages report "COMPLETED" internally (no pass/fail concept
        # of their own); display it as "PASS" for consistency with the other
        # stages and with the overall run status shown by list-runs.
        return "[pass]PASS[/pass]"
    return f"[secondary]{status or '—'}[/secondary]"
