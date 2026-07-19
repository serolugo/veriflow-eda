"""Vivado xsim simulation backend.

Unlike icarus (a single `iverilog` compile + `vvp` run), Vivado's
simulation flow is three separate CLI tools chained together:

    xvlog  <sources>              -- compile into a work library
    xelab  <tb_top> -s <snapshot> -- elaborate into a named design snapshot
    xsim   <snapshot> --runall    -- load and run the elaborated snapshot

Each step's own log is appended, in order, to the same combined
sim_log_path -- a failure at step 1 or 2 still leaves a complete,
readable trail of what ran before it, and `xelab`/`xsim` are simply never
invoked once an earlier step has already failed.

See docs/CUSTOM_BACKENDS.md for the full contract this (and any other
custom commercial backend -- Xcelium, VCS, Questa, ...) must satisfy;
this file is referenced there as the worked example.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from veriflow.core.backends._tools import _check_tool
from veriflow.core.backends.base import SimulationBackend
from veriflow.core.log_parser import parse_sim_log

# Vivado's own diagnostic messages are consistently prefixed this way
# regardless of which tool (xvlog/xelab/xsim) emits them -- e.g.
# "ERROR: [xsim 43-3316] ..." or "Fatal: ...". This is a best-effort
# heuristic (no real Vivado install was available to verify the exact
# format against; adjust if a real log ever doesn't match) used only as
# a *second* signal alongside xsim's own exit code -- see
# `_has_fatal_error`'s docstring.
_FATAL_LOG_RE = re.compile(r"^\s*(ERROR|FATAL_ERROR|Fatal):", re.IGNORECASE | re.MULTILINE)

_SNAPSHOT_NAME = "veriflow_sim_snapshot"
_VCD_FILENAME = "waves.vcd"


def _resolve(tool: str) -> str:
    """Return shutil.which(tool)'s resolved path, falling back to the bare
    name if not found at all.

    Same fix as `_check_tool` (core/backends/_tools.py): on Windows,
    Vivado installs xvlog/xelab/xsim as a same-named extensionless file
    alongside a "<tool>.bat" launcher. shutil.which correctly finds the
    ".bat" (PATHEXT-aware search), but subprocess.run([tool, ...]) with
    the bare name re-resolves it via CreateProcess (shell=False), which
    doesn't apply PATHEXT the way shutil.which/cmd.exe do -- passing the
    bare name fails with FileNotFoundError ([WinError 2]) even though the
    tool is genuinely installed. Using the already-resolved path fixes
    this on every platform (a no-op on Linux/macOS). Falling back to the
    bare name when not found at all preserves today's behavior for a
    genuinely-missing tool -- subprocess.run raises FileNotFoundError,
    same as before this fix; that case is meant to be caught upstream via
    check_availability()/validate_tools(), not silently handled here.
    """
    return shutil.which(tool) or tool


def _section(step: str, result: subprocess.CompletedProcess) -> str:
    header = f"=== {step} (exit code {result.returncode}) ==="
    body = (result.stdout or "") + (result.stderr or "")
    return f"{header}\n{body}\n"


def _has_fatal_error(log_text: str) -> bool:
    """Second PASS/FAIL signal alongside xsim's own exit code.

    Real EDA tools occasionally return exit code 0 even when the
    simulation hit a runtime fatal error partway through (the process
    itself didn't crash, the *design under test* did) -- checking the log
    for Vivado's own error-message prefixes catches that case, the same
    "don't trust a single signal in isolation" principle
    `docs/CUSTOM_BACKENDS.md` asks every custom backend to follow.
    """
    return bool(_FATAL_LOG_RE.search(log_text))


class XsimSimulationBackend(SimulationBackend):
    def run_simulation(
        self,
        rtl_files: list[Path],
        tb_files: list[Path],
        tb_top: str,
        sim_log_path: Path,
        wave_path: Path,
    ) -> tuple[str, dict]:
        sim_log_path.parent.mkdir(parents=True, exist_ok=True)
        wave_path.parent.mkdir(parents=True, exist_ok=True)

        # All three steps run from the same temp work directory --
        # xvlog/xelab/xsim all write scratch state there (xsim.dir/,
        # .Xil/, *.pb, ...) that must never land in the project directory.
        # xsim in particular *requires* this: xelab's elaborated snapshot
        # is looked up relative to xsim's own cwd, so step 3 cannot be
        # relocated to wave_path.parent the way icarus's vvp step is --
        # see the VCD copy-back step below for how the waveform still
        # ends up in the right place despite that constraint.
        tmp_dir = Path(tempfile.mkdtemp(prefix="veriflow_xsim_"))
        log_parts: list[str] = []

        try:
            # 1. xvlog -- compile RTL + TB sources together (same "compile
            # everything, select the TB top explicitly via -s" policy as
            # icarus: no injection, no hidden include paths, no temp TB
            # sources).
            compile_cmd = (
                [_resolve("xvlog")]
                + [f.as_posix() for f in rtl_files]
                + [f.as_posix() for f in tb_files]
            )
            compile_result = subprocess.run(
                compile_cmd, capture_output=True, text=True, cwd=str(tmp_dir),
            )
            log_parts.append(_section("xvlog", compile_result))
            if compile_result.returncode != 0:
                sim_log_path.write_text("".join(log_parts), encoding="utf-8")
                return "FAILED", {"sim_time": "", "seed": ""}

            # 2. xelab -- elaborate the testbench top into a named snapshot.
            elab_cmd = [_resolve("xelab"), tb_top, "-s", _SNAPSHOT_NAME]
            elab_result = subprocess.run(
                elab_cmd, capture_output=True, text=True, cwd=str(tmp_dir),
            )
            log_parts.append(_section("xelab", elab_result))
            if elab_result.returncode != 0:
                sim_log_path.write_text("".join(log_parts), encoding="utf-8")
                return "FAILED", {"sim_time": "", "seed": ""}

            # 3. xsim -- run the elaborated snapshot. --log writes xsim's
            # own simulation transcript to a file (more complete than
            # whatever it prints to stdout/stderr in --runall batch mode);
            # read it back and fold it into the combined log alongside
            # this step's own captured stdout/stderr.
            xsim_log_path = tmp_dir / "xsim_transcript.log"
            run_cmd = [_resolve("xsim"), _SNAPSHOT_NAME, "--runall", "--log", str(xsim_log_path)]
            run_result = subprocess.run(
                run_cmd, capture_output=True, text=True, cwd=str(tmp_dir),
            )
            log_parts.append(_section("xsim", run_result))
            if xsim_log_path.exists():
                log_parts.append(
                    "=== xsim transcript ===\n"
                    + xsim_log_path.read_text(encoding="utf-8", errors="replace")
                    + "\n"
                )

            combined_log = "".join(log_parts)
            sim_log_path.write_text(combined_log, encoding="utf-8")

            # The TB's own `$dumpfile("waves.vcd")` call (a relative path,
            # same hardcoded convention icarus's TBs rely on) dumps into
            # whatever xsim's cwd was -- tmp_dir here, not wave_path's real
            # location -- so copy it into place afterward.
            produced_vcd = tmp_dir / _VCD_FILENAME
            if produced_vcd.is_file():
                shutil.copy2(produced_vcd, wave_path)

            parsed = parse_sim_log(combined_log)
            status = (
                "COMPLETED"
                if run_result.returncode == 0 and not _has_fatal_error(combined_log)
                else "FAILED"
            )
            return status, parsed
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def check_availability(self) -> list[dict]:
        return [
            _check_tool("xvlog", version_flag="-version"),
            _check_tool("xelab", version_flag="-version"),
            _check_tool("xsim", version_flag="-version"),
        ]
