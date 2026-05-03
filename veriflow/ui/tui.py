"""
veriflow.ui.tui
───────────────
Redirige al TUI de tilebench (modo VeriFlow).
Requiere que tilebench esté instalado.
"""
from pathlib import Path


def run_tui(workspace: Path = Path(".")) -> None:
    from tilebench.tui.selector import run_veriflow
    run_veriflow(workspace=None)  # None → _get_workspace() detecta /workspace en Docker
