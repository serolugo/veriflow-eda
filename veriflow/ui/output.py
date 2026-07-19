"""
veriflow.ui.output
------------------
Styled output helpers used by all VeriFlow commands.
"""

from pathlib import Path
from rich.console import Console
from rich.markup import escape as _escape_markup
from rich.table import Table
from rich.text import Text
from rich.box import Box

from veriflow.ui.theme import (
    VERIFLOW_THEME,
    BLUE, GREEN, ORANGE, RED, GREY, WHITE,
    STYLE_PASS, STYLE_FAIL, STYLE_WARN, STYLE_ERROR,
    STYLE_ID, STYLE_SECONDARY,
)

console = Console(theme=VERIFLOW_THEME)

# box.SIMPLE_HEAD's top/bottom edges are blank (space-filled); rendering them
# (show_edge=True) would reintroduce a blank line, and leaving them off
# (show_edge=False) means the header has no rule *above* it, only below --
# the two rules end up different widths (title-separator's fixed 44 chars vs
# the table's own adaptive width). This custom box gives the table a real
# top rule identical in style/width to its head-row rule, both auto-sized
# together by Rich, so "line above header" == "line below header" always.
_FRAMED_HEAD_BOX = Box(
    " -- \n"
    "    \n"
    " -- \n"
    "    \n"
    "    \n"
    "    \n"
    "    \n"
    " -- \n"
)
error_console = Console(theme=VERIFLOW_THEME, stderr=True)


# ── Status indicators ──────────────────────────────────────────────────────────

def _dot_line(label: str, status: str, detail: str = "") -> Text:
    """Single result line:  label .......... STATUS  [detail]"""
    width = 42
    dots_n = max(4, width - len(label))
    dots = Text("·" * dots_n + " ", style=STYLE_SECONDARY)

    t = Text()
    t.append(f"  {label} ", style=f"bold {WHITE}")
    t.append_text(dots)

    if status == "PASS":
        t.append("PASS", style=STYLE_PASS)
    elif status == "FAIL":
        t.append("FAIL", style=STYLE_FAIL)
    elif status == "SKIP":
        t.append("SKIP", style=STYLE_SECONDARY)
    elif status == "RUN":
        t.append("···", style=STYLE_SECONDARY)
    else:
        t.append(status, style=STYLE_SECONDARY)

    if detail:
        t.append(f"  [{detail}]", style=STYLE_SECONDARY)

    return t


def print_status(label: str, status: str, detail: str = "") -> None:
    console.print(_dot_line(label, status, detail))


def print_warn(message: str) -> None:
    console.print(f"  [warn]![/warn]  [secondary]{message}[/secondary]")


def print_error(message: str) -> None:
    console.print(f"\n  [error]Error:[/error] {message}\n")


def print_cli_error(message: str) -> None:
    """Print the top-level `[ERROR] <message>` line used by the CLI's central
    error handler (cli.py), in pastel red, to stderr.

    *message* comes from a VeriFlowError raised anywhere in the codebase --
    not a fixed string this module controls -- so it's escaped before
    interpolation: an unescaped `[...]` inside it (e.g. a literal
    "pip install veriflow-eda[mcp]") would otherwise be parsed as Rich
    markup and silently swallowed instead of printed."""
    error_console.print(f"[error]\\[ERROR][/error] {_escape_markup(message)}")


def print_step(prefix: str, message: str) -> None:
    """Print a `[prefix] message` progress line (e.g. "[bump-version] ...")."""
    console.print(f"  [secondary]\\[{prefix}][/secondary] {message}")


def print_fail_detail(message: str, log_path: Path | None = None) -> None:
    """Show the relevant error line + path to full log."""
    console.print(f"    [secondary]->[/secondary] [fail]{message}[/fail]")
    if log_path:
        console.print(f"    [secondary]-> full log: {log_path}[/secondary]")


# ── Section headers ────────────────────────────────────────────────────────────

def print_run_header(db: Path, tile_id: str, run_id: str) -> None:
    console.print()
    console.print(f"  [secondary]database[/secondary]  [id]{db}[/id]")
    console.print(f"  [secondary]tile    [/secondary]  [id]{tile_id}[/id]")
    console.print(f"  [secondary]run     [/secondary]  [id]{run_id}[/id]")
    console.print()


def print_section(title: str) -> None:
    console.print(f"\n  [label]{title}[/label]")
    console.print(f"  [secondary]{'-' * 44}[/secondary]")


def print_title(title: str) -> None:
    """Print a section title with no separator line -- used before a Rich
    Table, which draws its own top rule (see print_tiles_table/print_runs_table)
    so the rule above the header matches the rule below it in width."""
    console.print(f"\n  [label]{title}[/label]")


# ── Tables ─────────────────────────────────────────────────────────────────────

def print_ports_table(ports: list[dict]) -> None:
    """Render a port list as a styled table."""
    table = Table(
        box=_FRAMED_HEAD_BOX,
        show_header=True,
        header_style=f"bold {BLUE}",
        border_style=GREY,
        padding=(0, 2),
        show_edge=True,
    )
    table.add_column("Name",      style=WHITE)
    table.add_column("Direction", style=GREY)
    table.add_column("Width",     style=GREY, justify="right")

    for p in ports:
        table.add_row(p["name"], p["direction"], str(p["width"]))

    console.print()
    console.print(table)


def print_tiles_table(rows: list[tuple[str, str, str, str, str, str]]) -> None:
    """Render tile rows as a styled table.

    Columns: #, Tile ID, Name, Author, Ver, Interface. Column widths are
    adaptive (Rich sizes each column to its content automatically).
    """
    table = Table(
        box=_FRAMED_HEAD_BOX,
        show_header=True,
        header_style=f"bold {BLUE}",
        border_style=GREY,
        padding=(0, 2),
        show_edge=True,
    )
    table.add_column("#",         style=BLUE)
    table.add_column("Tile ID",   style=GREY)
    table.add_column("Name",      style=WHITE)
    table.add_column("Author",    style=GREY)
    table.add_column("Ver",       style=GREY)
    table.add_column("Interface", style=GREY)

    for number, tile_id, name, author, ver, interface in rows:
        table.add_row(number, tile_id, name, author, ver, interface)

    console.print(table)


def print_runs_table(rows: list[tuple[str, str, str, str]]) -> None:
    """Render run rows as a styled table.

    Columns: Run, Status, Date, Wave. `status`/`wave` entries are expected
    to already carry Rich markup (e.g. "[pass]PASS[/pass]") -- the caller
    resolves status/wave coloring since it knows the domain status values.
    """
    table = Table(
        box=_FRAMED_HEAD_BOX,
        show_header=True,
        header_style=f"bold {BLUE}",
        border_style=GREY,
        padding=(0, 2),
        show_edge=True,
    )
    table.add_column("Run",    style=BLUE)
    table.add_column("Status")
    table.add_column("Date",   style=GREY)
    table.add_column("Wave")

    for run_id, status, date_str, wave in rows:
        table.add_row(run_id, status, date_str, wave)

    console.print(table)


def print_file_tree(files: list[Path], root: Path) -> None:
    """Show generated files as a simple tree."""
    console.print()
    for f in files:
        try:
            rel = f.relative_to(root)
        except ValueError:
            rel = f
        console.print(f"  [secondary]  {rel}[/secondary]")
    console.print()


# ── Waveform link ──────────────────────────────────────────────────────────────

def print_wave_url(url: str) -> None:
    console.print()
    console.print(f"  [pass]+[/pass] [label]Waveform ready[/label]")
    console.print(f"  [secondary]  Open in browser ->[/secondary] [link]{url}[/link]")
    console.print()


# ── Generic success / done ─────────────────────────────────────────────────────

def print_done(message: str) -> None:
    console.print(f"\n  [pass]+[/pass]  {message}\n")
