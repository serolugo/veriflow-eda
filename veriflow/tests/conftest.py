import shutil

import pytest


def _tool_available(name: str) -> bool:
    return shutil.which(name) is not None


IVERILOG_AVAILABLE = _tool_available("iverilog")
YOSYS_AVAILABLE = _tool_available("yosys")

skip_no_iverilog = pytest.mark.skipif(
    not IVERILOG_AVAILABLE,
    reason="iverilog not found in PATH",
)
skip_no_yosys = pytest.mark.skipif(
    not YOSYS_AVAILABLE,
    reason="yosys not found in PATH",
)
