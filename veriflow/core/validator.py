import shutil
import subprocess
from pathlib import Path

import yaml

from veriflow.core import VeriFlowError
from veriflow.models.project_config import ProjectConfig
from veriflow.models.tile_config import TileConfig


def validate_database(db: Path) -> None:
    """Validate that the database directory has all required files."""
    for name, is_file in [
        ("project_config.yaml", True),
        ("tile_index.csv", True),
        ("records.csv", True),
        ("tiles", False),
    ]:
        target = db / name
        if not target.exists():
            raise VeriFlowError(
                f"Required {'file' if is_file else 'directory'} not found: {target}",
                code="VF_DB_MISSING_REQUIRED_PATH",
                details={"path": str(target), "name": name},
            )


def validate_tools(
    need_iverilog: bool = True,
    need_yosys: bool = True,
) -> None:
    """Validate that required EDA tools are available in PATH.

    Pass need_iverilog=False to skip the iverilog check (e.g. synth-only runs),
    or need_yosys=False to skip the yosys check (e.g. connectivity/sim-only runs).
    """
    tools = []
    if need_iverilog:
        tools.append("iverilog")
    if need_yosys:
        tools.append("yosys")
    for tool in tools:
        if shutil.which(tool) is None:
            raise VeriFlowError(
                f"Tool not found in PATH: {tool}\n"
                f"  Install OSS CAD Suite and ensure it is on your PATH.",
                code="VF_TOOL_NOT_FOUND",
                details={"tool": tool},
            )


def validate_run_inputs(
    db: Path,
    tile_number_str: str,
    tile_config: TileConfig,
) -> None:
    """Validate all inputs required for a run command."""
    config_dir = db / "config" / f"tile_{tile_number_str}"
    if not config_dir.exists():
        raise VeriFlowError(f"Config directory not found: {config_dir}")

    rtl_dir = config_dir / "src" / "rtl"
    if not rtl_dir.exists() or not any(rtl_dir.glob("*.v")):
        raise VeriFlowError(
            f"No .v files found in RTL source directory: {rtl_dir}",
            code="VF_INPUT_RTL_MISSING",
            details={"rtl_dir": str(rtl_dir)},
        )

    if not tile_config.top_module:
        raise VeriFlowError(
            "top_module is empty in tile_config.yaml",
            code="VF_INPUT_TOP_MODULE_MISSING",
        )

    # Verify a .v file whose stem matches top_module exists
    top_file = rtl_dir / f"{tile_config.top_module}.v"
    if not top_file.exists():
        raise VeriFlowError(
            f"No .v file found for top_module={tile_config.top_module!r} in {rtl_dir}\n"
            f"  Expected: {top_file}",
            code="VF_INPUT_TOP_MODULE_FILE_MISSING",
            details={"top_module": tile_config.top_module, "expected_file": str(top_file)},
        )


def validate_project_config(project_config: ProjectConfig) -> None:
    """Validate that required fields in project_config are set."""
    if not project_config.id_prefix:
        raise VeriFlowError("id_prefix is empty in project_config.yaml")


def detect_iverilog_version() -> str:
    """Run iverilog -V and return parsed version string."""
    from veriflow.core.log_parser import parse_iverilog_version
    try:
        result = subprocess.run(
            ["iverilog", "-V"],
            capture_output=True,
            text=True,
        )
        output = result.stdout + result.stderr
        return parse_iverilog_version(output)
    except Exception:
        return "unknown"
