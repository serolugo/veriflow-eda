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
from typing import Optional

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


def wrap_init(
    interface_name: str,
    rtl_file: "str | Path",
    *,
    wrapper_name: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> dict:
    """Scaffold a wrapper config dict from a single RTL file.

    Reads *rtl_file* and auto-detects the top module name (requires exactly
    one module declaration in the file). Extracts IP ports (3-tuples
    name/direction/width, N10), and returns a dict matching the
    wrapper_config.yaml schema.
    Does NOT write any files.

    The returned dict also contains a private ``"_ip_ports"`` key (list of
    3-tuples) that cmd_wrap_init uses to render the commented YAML scaffold.
    Callers that only need the config dict can ignore it.

    Raises:
        VeriFlowError(VF_INTERFACE_UNKNOWN)              -- interface not registered
        VeriFlowError(VF_WRAP_E_NO_MODULE_FOUND)         -- file has no module declaration
        VeriFlowError(VF_WRAP_E_MULTIPLE_MODULES_FOUND)  -- file has 2+ module declarations
    """
    import re
    from veriflow.core.wrapper.port_parser import extract_ports
    from veriflow.models.interface_profile import get_interface_profile

    # Validate interface_name early -- raises VF_INTERFACE_UNKNOWN if not registered
    get_interface_profile(interface_name)

    rtl_path = Path(rtl_file)
    text = rtl_path.read_text(encoding="utf-8")

    # Auto-detect module name from the file
    module_re = re.compile(r"\bmodule\s+(\w+)", re.IGNORECASE)
    found = module_re.findall(text)
    seen: set = set()
    modules: list = []
    for name in found:
        if name not in seen:
            seen.add(name)
            modules.append(name)

    if len(modules) == 0:
        raise VeriFlowError(
            f"No module declaration found in {rtl_path}.",
            code="VF_WRAP_E_NO_MODULE_FOUND",
            details={"rtl_file": str(rtl_path)},
        )
    if len(modules) > 1:
        raise VeriFlowError(
            f"Multiple module declarations found in {rtl_path}: "
            f"{', '.join(modules)}. "
            "Auto-detection requires exactly one module per file. "
            "Move the top module to its own file before running wrap init.",
            code="VF_WRAP_E_MULTIPLE_MODULES_FOUND",
            details={"rtl_file": str(rtl_path), "modules": modules},
        )

    top_module = modules[0]
    ip_ports = extract_ports(text, top_module)
    meta = dict(metadata) if metadata else {}

    return {
        "interface_name": interface_name,
        "metadata": {
            "name": meta.get("name", top_module),
            "author": meta.get("author", ""),
            "description": meta.get("description", ""),
            "version": meta.get("version", "1.0.0"),
        },
        "design": {
            "top_module": top_module,
            "rtl_sources": [str(rtl_path)],
        },
        "wrapper_name": wrapper_name or f"{top_module}_wrapper",
        "ports": {name: None for name, _, _ in ip_ports},
        "_ip_ports": ip_ports,  # private -- for cmd_wrap_init; not a YAML schema key
    }



def wrap_generate(
    config_path: str | Path,
    out_dir: Optional[str | Path] = None,
) -> dict:
    """Run veriflow wrap generate for *config_path*.

    Returns the full output dict (schema_version, status, ports, …).
    VeriFlowError propagates unchanged for config-level errors (missing
    interface_name, top_module not found in RTL, etc.).
    Validation FAIL is returned as a dict with status="FAIL" — not raised.
    """
    from veriflow.workflows.wrap import WrapWorkflow

    return WrapWorkflow().generate(
        config_path=Path(config_path),
        out_dir=Path(out_dir) if out_dir is not None else None,
    )
