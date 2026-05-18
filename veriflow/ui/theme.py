"""
veriflow.ui.theme
-----------------
Central color palette and Rich styles.
All UI modules import from here — change colors in one place.
"""

from rich.style import Style
from rich.theme import Theme

# ── Pastel palette ─────────────────────────────────────────────────────────────
BLUE    = "#7EB8D4"   # IDs, headers, database names
GREEN   = "#87D4A0"   # PASS, success, TileWizard accent
ORANGE  = "#D4956A"   # VeriFlow accent, warnings
RED     = "#D47E7E"   # FAIL, errors
GREY    = "#888888"   # secondary text, dots, separators
WHITE   = "#E8E8E8"   # primary text

# ── Named styles ───────────────────────────────────────────────────────────────
STYLE_PASS      = Style(color=GREEN,  bold=True)
STYLE_FAIL      = Style(color=RED,    bold=True)
STYLE_WARN      = Style(color=ORANGE, bold=False)
STYLE_ERROR     = Style(color=RED,    bold=True)
STYLE_ID        = Style(color=BLUE)
STYLE_SECONDARY = Style(color=GREY)
STYLE_LABEL     = Style(color=WHITE,  bold=True)

# VeriFlow orange vs TileWizard green subtitles
STYLE_VERIFLOW   = Style(color=ORANGE, bold=True)
STYLE_TILEWIZARD = Style(color=GREEN,  bold=True)

# ── Rich Theme (used by Console) ───────────────────────────────────────────────
VERIFLOW_THEME = Theme({
    "pass":       f"bold {GREEN}",
    "fail":       f"bold {RED}",
    "warn":       ORANGE,
    "error":      f"bold {RED}",
    "id":         BLUE,
    "secondary":  GREY,
    "label":      f"bold {WHITE}",
    "veriflow":   f"bold {ORANGE}",
    "tilewizard": f"bold {GREEN}",
    "link":       f"underline {BLUE}",
})
