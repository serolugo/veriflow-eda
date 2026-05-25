"""
veriflow.api — Internal Python integration surface for VeriFlow.

Use this module to call VeriFlow from another Python process, TUI, CI
script, or agent without depending on cli.py internals or subprocess.

    from veriflow.api import run_tile
    result = run_tile("./database", "0001", skip_sim=True, skip_synth=True)

VeriFlowError is re-raised directly; callers should import it from
veriflow.core if they need to catch it.
"""

from __future__ import annotations

from pathlib import Path

from veriflow.core import VeriFlowError


def normalize_path(db_path: str | Path) -> Path:
    return Path(db_path)


def run_tile(
    db_path: str | Path,
    tile: str,
    *,
    skip_connectivity: bool = False,
    skip_sim: bool = False,
    skip_synth: bool = False,
    only_connectivity: bool = False,
    only_sim: bool = False,
    only_synth: bool = False,
    waves: bool = False,
    non_interactive: bool = False,
) -> dict:
    """Run the verification pipeline for *tile* and return the run_result dict.

    Delegates to cmd_run(); does not duplicate logic.
    VeriFlowError propagates to the caller unchanged.

    Parameters
    ----------
    db_path : str | Path
        Path to the VeriFlow database directory.
    tile : str
        Four-digit tile number as a string (e.g. "0001").
    skip_connectivity, skip_sim, skip_synth : bool
        Skip individual stages.
    only_connectivity, only_sim, only_synth : bool
        Run a single stage; remaining stages are skipped.
    waves : bool
        Launch waveform viewer after simulation.
    non_interactive : bool
        When True, disables the waveform viewer (raises VeriFlowError if
        waves=True is also requested).
    """
    if non_interactive and waves:
        raise VeriFlowError(
            "Waveform viewer cannot be launched in non-interactive mode",
            code="VF_NON_INTERACTIVE_VIEWER_DISABLED",
            exit_code=2,
        )

    from veriflow.commands.run import cmd_run

    return cmd_run(
        db=normalize_path(db_path),
        tile_number=tile,
        skip_check=skip_connectivity,
        skip_sim=skip_sim,
        skip_synth=skip_synth,
        only_check=only_connectivity,
        only_sim=only_sim,
        only_synth=only_synth,
        waves=waves,
    )
