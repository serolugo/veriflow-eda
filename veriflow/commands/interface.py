"""`veriflow interface` -- manage the permanent local cache of URL-sourced
interface definitions (`interface.definition: http(s)://...`).

Mirrors `veriflow pdk`'s "fetch once, use from cache forever, update
explicitly" philosophy (see `veriflow.models.pdk_manager`): a URL is
downloaded exactly once, on first use, and never re-fetched implicitly --
`veriflow interface update <name>` is the only thing that re-downloads.
"""

from __future__ import annotations

import argparse

from rich import box
from rich.table import Table

from veriflow.models.interface_profile import (
    VERIFLOW_INTERFACES_CACHE_ROOT,
    list_cached_interface_urls,
    update_cached_interface_url,
)
from veriflow.ui.output import console, print_done
from veriflow.ui.theme import BLUE, GREY, WHITE


def cmd_interface_update(args: argparse.Namespace) -> int:
    """Implement `veriflow interface update <name>`.

    VeriFlowError(VF_INTERFACE_UPDATE_NOT_FOUND) propagates to cli.py when
    *name* has no cached URL-based definition (never downloaded, or it's a
    built-in / local-file profile with nothing to re-fetch).
    """
    name = args.name
    source_url = update_cached_interface_url(name)
    print_done(f"Updated interface [id]{name}[/id] from [id]{source_url}[/id]")
    return 0


def cmd_interface_list_cached(args: argparse.Namespace) -> tuple[int, dict]:
    entries = list_cached_interface_urls()

    table = Table(
        box=box.SIMPLE,
        show_header=True,
        header_style=f"bold {BLUE}",
        border_style=GREY,
        padding=(0, 2),
    )
    table.add_column("Interface", style=WHITE)
    table.add_column("Source URL", style=GREY)
    table.add_column("Downloaded", style=GREY)

    for entry in entries:
        table.add_row(
            entry["name"],
            entry["url"],
            entry["downloaded_at"].strftime("%Y-%m-%d %H:%M:%S"),
        )

    console.print("\n  [label]Cached interface definitions[/label]")
    if entries:
        console.print(table)
    else:
        console.print("  [secondary]No cached URL-based interface definitions.[/secondary]")
    console.print(f"  [secondary]Cache root:[/secondary] {VERIFLOW_INTERFACES_CACHE_ROOT}")
    console.print()

    return 0, {
        "status": "SUCCESS",
        "command": "interface list-cached",
        "interfaces": [
            {**entry, "downloaded_at": entry["downloaded_at"].isoformat()}
            for entry in entries
        ],
        "cache_root": str(VERIFLOW_INTERFACES_CACHE_ROOT),
    }
