from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from veriflow.core.backends._tools import _check_tool
from veriflow.core.backends.base import SynthesisBackend
from veriflow.core.synth_runner import run_synthesis

if TYPE_CHECKING:
    from veriflow.models.technology_profile import TechnologyProfile


class YosysSynthesisBackend(SynthesisBackend):

    def run_synthesis(
        self,
        rtl_files: list[Path],
        top_module: str,
        synth_log_path: Path,
        technology: "TechnologyProfile | None" = None,
    ) -> tuple[str, dict]:
        return run_synthesis(
            rtl_files=rtl_files,
            top_module=top_module,
            synth_log_path=synth_log_path,
            technology=technology,
        )

    def check_availability(self) -> list[dict]:
        return [_check_tool("yosys")]
