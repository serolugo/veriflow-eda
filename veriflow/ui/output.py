"""
veriflow.ui.output
------------------
Styled output helpers used by all VeriFlow commands.
"""

from pathlib import Path
from rich.console import Console
from rich.table import Table
from rich.text import Text
from rich import box

from veriflow.ui.theme import (
    VERIFLOW_THEME,
    BLUE, GREEN, ORANGE, RED, GREY, WHITE,
    STYLE_PASS, STYLE_FAIL, STYLE_WARN, STYLE_ERROR,
    STYLE_ID, STYLE_SECONDARY,
)

console = Console(theme=VERIFLOW_THEME)


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
    console.print(f"  [warn]⚠[/warn]  [secondary]{message}[/secondary]")


def print_error(message: str) -> None:
    console.print(f"\n  [error]Error:[/error] {message}\n")


def print_fail_detail(message: str, log_path: Path | None = None) -> None:
    """Show the relevant error line + path to full log."""
    console.print(f"    [secondary]→[/secondary] [fail]{message}[/fail]")
    if log_path:
        console.print(f"    [secondary]→ full log: {log_path}[/secondary]")


# ── Section headers ────────────────────────────────────────────────────────────

def print_run_header(db: Path, tile_id: str, run_id: str) -> None:
    console.print()
    console.print(f"  [secondary]database[/secondary]  [id]{db}[/id]")
    console.print(f"  [secondary]tile    [/secondary]  [id]{tile_id}[/id]")
    console.print(f"  [secondary]run     [/secondary]  [id]{run_id}[/id]")
    console.print()


def print_section(title: str) -> None:
    console.print(f"\n  [label]{title}[/label]")
    console.print(f"  [secondary]{'─' * 44}[/secondary]")


# ── Tables ─────────────────────────────────────────────────────────────────────

def print_ports_table(ports: list[dict]) -> None:
    """Render a port list as a styled table."""
    table = Table(
        box=box.SIMPLE,
        show_header=True,
        header_style=f"bold {BLUE}",
        border_style=GREY,
        padding=(0, 2),
    )
    table.add_column("Name",      style=WHITE)
    table.add_column("Direction", style=GREY)
    table.add_column("Width",     style=GREY, justify="right")

    for p in ports:
        table.add_row(p["name"], p["direction"], str(p["width"]))

    console.print()
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
    console.print(f"  [pass]✓[/pass] [label]Waveform ready[/label]")
    console.print(f"  [secondary]  Open in browser →[/secondary] [link]{url}[/link]")
    console.print()


# ── Generic success / done ─────────────────────────────────────────────────────

def print_done(message: str) -> None:
    console.print(f"\n  [pass]✓[/pass]  {message}\n")
