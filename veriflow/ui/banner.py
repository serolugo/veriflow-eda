"""
veriflow.ui.banner
------------------
SEMICOLAB banner with pyfiglet + TerminalTextEffects MiddleOut animation.
Subtitle changes per tool: orange for VeriFlow, green for TileWizard.
Mifral link shown only on first run (tracked via ~/.semicolab_seen).
"""

import sys
import time
from pathlib import Path

from rich.console import Console
from rich.text import Text
from rich.align import Align

from veriflow.ui.theme import VERIFLOW_THEME, ORANGE, GREEN, BLUE, GREY, WHITE

console = Console(theme=VERIFLOW_THEME)

SEEN_FILE = Path.home() / ".semicolab_seen"
MIFRAL_URL = "https://www.mifral.com/en"


def _is_first_run() -> bool:
    return not SEEN_FILE.exists()


def _mark_seen() -> None:
    SEEN_FILE.touch()


def _render_figlet(text: str) -> str:
    try:
        import pyfiglet
        return pyfiglet.figlet_format(text, font="slant")
    except ImportError:
        return f"  {text}\n"


def _animate_middleout(text: str, color: str) -> None:
    """
    MiddleOut effect: reveal text from center outward, character by character.
    Falls back to instant print if TerminalTextEffects is not available.
    """
    try:
        from terminaltexteffects.effects.effect_middleout import MiddleOut
        from terminaltexteffects.utils.graphics import Color

        effect = MiddleOut(text)
        effect.effect_config.center_expand_color = Color(color.lstrip("#"))
        effect.effect_config.full_expand_color    = Color(WHITE.lstrip("#"))

        with effect.terminal_output(end_symbol=" ") as terminal:
            for frame in effect:
                terminal.print(frame)

    except Exception:
        # TerminalTextEffects not installed or failed — just print
        console.print(text, style=f"bold {color}")


def show_banner(subtitle: str, tool: str = "veriflow") -> None:
    """
    Print the SEMICOLAB banner.

    Parameters
    ----------
    subtitle : str
        Tool name shown below SEMICOLAB (e.g. "VeriFlow" or "TileBench").
    tool : str
        "veriflow" → orange accent  |  "tilewizard" → green accent
    """
    accent = ORANGE if tool == "veriflow" else GREEN
    figlet_text = _render_figlet("SEMICOLAB")

    console.print()
    _animate_middleout(figlet_text, color=accent)

    # Subtitle line
    sub = Text()
    sub.append(f"  {subtitle}", style=f"bold {accent}")
    sub.append("  ·  ", style=GREY)
    sub.append("SemiCoLab Toolchain", style=f"bold {WHITE}")
    console.print(sub)

    # Mifral link — only first time
    if _is_first_run():
        console.print()
        link_line = Text()
        link_line.append("  ", style="")
        link_line.append(MIFRAL_URL, style=f"underline {BLUE}")
        console.print(link_line)
        _mark_seen()

    console.print()
    console.print(f"  [secondary]{'─' * 50}[/secondary]")
    console.print()
