"""
veriflow.ui.themes
------------------
Color palettes ported from Argonaut (github.com/darksworm/argonaut).
Each theme maps to semantic keys used to generate Textual inline CSS.

Semantic keys
-------------
bg            : main background (darkest)
bg_panel      : panel / card background
bg_muted      : inactive / subtle background
text          : primary text
text_dim      : secondary text, timestamps, separators
accent        : focused border, primary selection highlight bg
blue          : breadcrumb, IDs, info
green         : PASS, TileWizard accent
orange        : VeriFlow accent, warnings
red           : FAIL, errors
yellow        : progress, pending
border        : unfocused panel border
selected_bg   : selected row background
cursor_bg     : cursor on unselected row
cursor_sel_bg : cursor on selected row
"""

from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path

THEME_FILE = Path.home() / ".semicolab_theme"
DEFAULT_THEME = "tokyo-night"


@dataclass(frozen=True)
class Palette:
    bg: str
    bg_panel: str
    bg_muted: str
    text: str
    text_dim: str
    accent: str
    blue: str
    green: str
    orange: str
    red: str
    yellow: str
    border: str
    selected_bg: str
    cursor_bg: str
    cursor_sel_bg: str


THEMES: dict[str, Palette] = {
    "tokyo-night": Palette(
        bg="#1a1b26",
        bg_panel="#1f2335",
        bg_muted="#24283b",
        text="#c0caf5",
        text_dim="#565f89",
        accent="#bb9af7",
        blue="#7dcfff",
        green="#9ece6a",
        orange="#ff9e64",
        red="#f7768e",
        yellow="#e0af68",
        border="#3b4261",
        selected_bg="#33467c",
        cursor_bg="#7dcfff",
        cursor_sel_bg="#7dcfff",
    ),
    "tokyo-storm": Palette(
        bg="#24283b",
        bg_panel="#24283b",
        bg_muted="#2f3449",
        text="#c0caf5",
        text_dim="#565f89",
        accent="#7aa2f7",
        blue="#7dcfff",
        green="#9ece6a",
        orange="#ff9e64",
        red="#f7768e",
        yellow="#e0af68",
        border="#3b4261",
        selected_bg="#3b4261",
        cursor_bg="#7dcfff",
        cursor_sel_bg="#7dcfff",
    ),
    "catppuccin-mocha": Palette(
        bg="#1e1e2e",
        bg_panel="#181825",
        bg_muted="#313244",
        text="#cdd6f4",
        text_dim="#6c7086",
        accent="#cba6f7",
        blue="#89dceb",
        green="#a6e3a1",
        orange="#fab387",
        red="#f38ba8",
        yellow="#f9e2af",
        border="#585b70",
        selected_bg="#313244",
        cursor_bg="#89dceb",
        cursor_sel_bg="#89b4fa",
    ),
    "catppuccin-latte": Palette(
        bg="#eff1f5",
        bg_panel="#ccd0da",
        bg_muted="#e6e9ef",
        text="#4c4f69",
        text_dim="#8c8fa1",
        accent="#8839ef",
        blue="#04a5e5",
        green="#40a02b",
        orange="#fe640b",
        red="#d20f39",
        yellow="#df8e1d",
        border="#acb0be",
        selected_bg="#ccd0da",
        cursor_bg="#1e66f5",
        cursor_sel_bg="#1e66f5",
    ),
    "dracula": Palette(
        bg="#282a36",
        bg_panel="#3a3c4e",
        bg_muted="#44475a",
        text="#f8f8f2",
        text_dim="#6272a4",
        accent="#bd93f9",
        blue="#8be9fd",
        green="#50fa7b",
        orange="#ffb86c",
        red="#ff5555",
        yellow="#f1fa8c",
        border="#bd93f9",
        selected_bg="#bd93f9",
        cursor_bg="#8be9fd",
        cursor_sel_bg="#8be9fd",
    ),
    "nord": Palette(
        bg="#2e3440",
        bg_panel="#2e3440",
        bg_muted="#3b4252",
        text="#e5e9f0",
        text_dim="#4c566a",
        accent="#88c0d0",
        blue="#81a1c1",
        green="#a3be8c",
        orange="#d08770",
        red="#bf616a",
        yellow="#ebcb8b",
        border="#434c5e",
        selected_bg="#3b4252",
        cursor_bg="#88c0d0",
        cursor_sel_bg="#88c0d0",
    ),
    "gruvbox-dark": Palette(
        bg="#282828",
        bg_panel="#32302f",
        bg_muted="#3c3836",
        text="#ebdbb2",
        text_dim="#a89984",
        accent="#d79921",
        blue="#458588",
        green="#98971a",
        orange="#d65d0e",
        red="#cc241d",
        yellow="#d79921",
        border="#504945",
        selected_bg="#3c3836",
        cursor_bg="#83a598",
        cursor_sel_bg="#83a598",
    ),
    "gruvbox-light": Palette(
        bg="#fbf1c7",
        bg_panel="#fbf1c7",
        bg_muted="#f2e5bc",
        text="#3c3836",
        text_dim="#7c6f64",
        accent="#b57614",
        blue="#076678",
        green="#79740e",
        orange="#af3a03",
        red="#9d0006",
        yellow="#b57614",
        border="#bdae93",
        selected_bg="#d5c4a1",
        cursor_bg="#076678",
        cursor_sel_bg="#076678",
    ),
    "one-dark": Palette(
        bg="#282c34",
        bg_panel="#21252b",
        bg_muted="#2c313c",
        text="#abb2bf",
        text_dim="#5c6370",
        accent="#61afef",
        blue="#56b6c2",
        green="#98c379",
        orange="#d19a66",
        red="#e06c75",
        yellow="#e5c07b",
        border="#3e4451",
        selected_bg="#3e4451",
        cursor_bg="#528bff",
        cursor_sel_bg="#528bff",
    ),
    "one-light": Palette(
        bg="#fafafa",
        bg_panel="#f7f7f7",
        bg_muted="#f3f3f3",
        text="#383a42",
        text_dim="#a0a1a7",
        accent="#4078f2",
        blue="#0184bc",
        green="#50a14f",
        orange="#986801",
        red="#e45649",
        yellow="#c18401",
        border="#d0d0d0",
        selected_bg="#e5eaf0",
        cursor_bg="#4078f2",
        cursor_sel_bg="#4078f2",
    ),
    "monokai": Palette(
        bg="#272822",
        bg_panel="#2d2e2a",
        bg_muted="#3e3d32",
        text="#f8f8f2",
        text_dim="#75715e",
        accent="#ae81ff",
        blue="#66d9ef",
        green="#a6e22e",
        orange="#fd971f",
        red="#f92672",
        yellow="#e6db74",
        border="#75715e",
        selected_bg="#49483e",
        cursor_bg="#66d9ef",
        cursor_sel_bg="#66d9ef",
    ),
    "solarized-dark": Palette(
        bg="#002b36",
        bg_panel="#002b36",
        bg_muted="#073642",
        text="#93a1a1",
        text_dim="#586e75",
        accent="#6c71c4",
        blue="#2aa198",
        green="#859900",
        orange="#cb4b16",
        red="#dc322f",
        yellow="#b58900",
        border="#073642",
        selected_bg="#073642",
        cursor_bg="#2aa198",
        cursor_sel_bg="#2aa198",
    ),
    "solarized-light": Palette(
        bg="#fdf6e3",
        bg_panel="#fdf6e3",
        bg_muted="#eee8d5",
        text="#657b83",
        text_dim="#93a1a1",
        accent="#6c71c4",
        blue="#2aa198",
        green="#859900",
        orange="#cb4b16",
        red="#dc322f",
        yellow="#b58900",
        border="#93a1a1",
        selected_bg="#eee8d5",
        cursor_bg="#2aa198",
        cursor_sel_bg="#2aa198",
    ),
    "oxocarbon": Palette(
        bg="#161616",
        bg_panel="#393939",
        bg_muted="#262626",
        text="#f2f4f8",
        text_dim="#8d8d8d",
        accent="#be95ff",
        blue="#3ddbd9",
        green="#42be65",
        orange="#ff832b",
        red="#fa4d56",
        yellow="#f1c21b",
        border="#be95ff",
        selected_bg="#be95ff",
        cursor_bg="#3ddbd9",
        cursor_sel_bg="#3ddbd9",
    ),
    "high-contrast": Palette(
        bg="#000000",
        bg_panel="#0d0d0d",
        bg_muted="#1a1a1a",
        text="#ffffff",
        text_dim="#bfbfbf",
        accent="#00ffff",
        blue="#00ffff",
        green="#00ff00",
        orange="#ff8800",
        red="#ff0033",
        yellow="#ffff00",
        border="#ffffff",
        selected_bg="#333333",
        cursor_bg="#ffffff",
        cursor_sel_bg="#00ffff",
    ),
    "colorblind-safe": Palette(
        bg="#161616",
        bg_panel="#1e1e1e",
        bg_muted="#252525",
        text="#eaeaea",
        text_dim="#a8a8a8",
        accent="#cc79a7",
        blue="#56b4e9",
        green="#009e73",
        orange="#e69f00",
        red="#d55e00",
        yellow="#f0e442",
        border="#a8a8a8",
        selected_bg="#303030",
        cursor_bg="#56b4e9",
        cursor_sel_bg="#56b4e9",
    ),
}

THEME_LABELS = {
    "tokyo-night":      "Tokyo Night",
    "tokyo-storm":      "Tokyo Storm",
    "catppuccin-mocha": "Catppuccin Mocha",
    "catppuccin-latte": "Catppuccin Latte",
    "dracula":          "Dracula",
    "nord":             "Nord",
    "gruvbox-dark":     "Gruvbox Dark",
    "gruvbox-light":    "Gruvbox Light",
    "one-dark":         "One Dark",
    "one-light":        "One Light",
    "monokai":          "Monokai",
    "solarized-dark":   "Solarized Dark",
    "solarized-light":  "Solarized Light",
    "oxocarbon":        "Oxocarbon",
    "high-contrast":    "High Contrast",
    "colorblind-safe":  "Colorblind Safe",
}


def get_palette(name: str | None = None) -> Palette:
    """Return the Palette for *name*, falling back to the saved theme then default."""
    if name is None:
        name = load_theme()
    return THEMES.get(name, THEMES[DEFAULT_THEME])


def palette_to_vars(palette: Palette) -> dict[str, str]:
    """Return a dict of CSS variable values for the given palette.

    Keys are used as var(--tb-<key>) in the CSS template.
    Textual injects these via App.get_css_variables().
    """
    return {
        "tb-bg":           palette.bg,
        "tb-bg-panel":     palette.bg_panel,
        "tb-bg-muted":     palette.bg_muted,
        "tb-text":         palette.text,
        "tb-text-dim":     palette.text_dim,
        "tb-accent":       palette.accent,
        "tb-blue":         palette.blue,
        "tb-green":        palette.green,
        "tb-orange":       palette.orange,
        "tb-red":          palette.red,
        "tb-yellow":       palette.yellow,
        "tb-border":       palette.border,
        "tb-selected-bg":  palette.selected_bg,
        "tb-cursor-bg":    palette.cursor_bg,
        "tb-cursor-sel":   palette.cursor_sel_bg,
    }


def build_css(palette: Palette) -> str:
    """Generate Textual inline CSS with hardcoded hex values (used at startup)."""
    p = palette
    return f"""
Screen {{
    background: {p.bg};
    color: {p.text};
}}
.panel {{
    border: round {p.border};
    background: {p.bg};
}}
.panel--focused {{
    border: round {p.accent};
}}
.panel--title {{
    color: {p.blue};
    text-style: bold;
}}
ListView {{
    background: {p.bg};
}}
ListItem {{
    background: {p.bg};
    color: {p.text};
}}
ListItem.--highlight {{
    background: {p.selected_bg};
    color: {p.text};
}}
.status--pass  {{ color: {p.green};  text-style: bold; }}
.status--fail  {{ color: {p.red};    text-style: bold; }}
.status--warn  {{ color: {p.yellow}; }}
.breadcrumb    {{ color: {p.blue};   }}
.text--dim     {{ color: {p.text_dim}; }}
Footer {{
    background: {p.bg_muted};
    color: {p.text_dim};
}}
"""


def build_css_vars() -> str:
    """CSS template using var(--tb-X) — used with get_css_variables() for live theming."""
    return """
Screen {
    background: var(--tb-bg);
    color: var(--tb-text);
}
.panel {
    border: round var(--tb-border);
    background: var(--tb-bg);
}
.panel.active {
    border: round var(--tb-accent);
}
ListView {
    background: var(--tb-bg);
    scrollbar-background: var(--tb-bg);
    scrollbar-color: var(--tb-border);
    height: 1fr;
}
ListView > ListItem {
    padding: 0 1;
    color: var(--tb-text);
    background: var(--tb-bg);
}
ListView > ListItem.--highlight {
    background: var(--tb-selected-bg);
    color: var(--tb-text);
    text-style: bold;
}
.run-pass { color: var(--tb-green); }
.run-fail { color: var(--tb-red);   }
.run-warn { color: var(--tb-yellow); }
.col-empty {
    width: 1fr;
    height: 1fr;
    align: center middle;
    color: var(--tb-text-dim);
}
Footer {
    background: var(--tb-bg-muted);
    color: var(--tb-text-dim);
}
"""


def save_theme(name: str) -> None:
    THEME_FILE.write_text(name, encoding="utf-8")


def load_theme() -> str:
    try:
        name = THEME_FILE.read_text(encoding="utf-8").strip()
        return name if name in THEMES else DEFAULT_THEME
    except FileNotFoundError:
        return DEFAULT_THEME
