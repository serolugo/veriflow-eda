# Adding a custom EDA backend

VeriFlow ships three built-in backends — `icarus` (connectivity +
simulation), `xsim` (simulation, Vivado), and `yosys` (synthesis) — but the
backend layer is a small, explicit contract, not a hardcoded assumption.
Adding support for a commercial tool (Cadence Xcelium, Synopsys VCS,
Siemens Questa, or anything else with a CLI) means writing one class and
adding one line to a registry — nothing in `core/stages/`,
`workflows/`, or the CLI needs to change.

This document is the reference for that contract, using the real
`XsimSimulationBackend` (`veriflow/core/backends/xsim.py`) as the worked
example throughout.

---

## 1. The three base-class contracts

`veriflow/core/backends/base.py` defines three abstract base classes —
implement the one matching what your tool does. A tool that does more
than one job (e.g. a simulator that also elaborates for connectivity
checking) gets one class per role; nothing requires a 1:1 mapping
between "backend classes" and "EDA tools".

```python
class ConnectivityBackend(abc.ABC):
    @abc.abstractmethod
    def run_connectivity(
        self,
        rtl_files: list[Path],
        interface_profile: object,   # an InterfaceProfile (see models/interface_profile.py)
        top_module: str,
        log_path: Path,
    ) -> str:
        """Returns 'PASS' or 'FAIL'."""

    @abc.abstractmethod
    def check_availability(self) -> list[dict]: ...


class SimulationBackend(abc.ABC):
    @abc.abstractmethod
    def run_simulation(
        self,
        rtl_files: list[Path],
        tb_files: list[Path],
        tb_top: str,           # testbench top module name, explicitly selected
        sim_log_path: Path,    # write your combined log here
        wave_path: Path,       # where the waveform (VCD) should end up
    ) -> tuple[str, dict]:
        """Returns ('COMPLETED'|'FAILED', parsed_dict).

        parsed_dict feeds results.json's per-stage "metrics" -- at minimum
        return {"sim_time": "", "seed": ""} (empty strings when unknown,
        never omit the keys)."""

    @abc.abstractmethod
    def check_availability(self) -> list[dict]: ...


class SynthesisBackend(abc.ABC):
    @abc.abstractmethod
    def run_synthesis(
        self,
        rtl_files: list[Path],
        top_module: str,
        synth_log_path: Path,
        technology: "TechnologyProfile | None" = None,
    ) -> tuple[str, dict]:
        """Returns ('PASS'|'FAIL', parsed_dict) -- parsed_dict feeds
        results.json's synthesis metrics: {"cells": str, "warnings": str,
        "errors": str, "has_latches": bool}."""

    @abc.abstractmethod
    def check_availability(self) -> list[dict]: ...
```

Notes that apply to all three:

- **Statuses are exact strings.** Connectivity/synthesis use `"PASS"`/`"FAIL"`;
  simulation uses `"COMPLETED"`/`"FAILED"` (a pre-existing, intentional
  inconsistency — simulation has no inherent pass/fail concept of its own,
  the *display* layer normalizes `"COMPLETED"` to `"PASS"` for the CLI/
  results view; your backend must still return the literal strings above,
  not the normalized ones).
- **Never raise for "the RTL failed verification."** A failing compile,
  elaboration, or run is data (`"FAIL"`/`"FAILED"`), not an exception —
  exceptions are reserved for "this backend genuinely could not attempt
  the check at all" (tool crashed unexpectedly, required input missing).
  Raising `VeriFlowError` from inside `run_*` stops the entire pipeline
  run and skips writing `results.json` for that attempt — appropriate for
  a hard environment problem, wrong for "the design didn't pass."
- **Write the log file yourself, always** — even on failure, even before
  raising anything. `sim_log_path`/`synth_log_path`/`log_path` is what
  users and `veriflow db show-run` read to understand what happened;
  a `"FAIL"` with no log is far more frustrating to debug than a `"FAIL"`
  with one.
- **No abstract `__init__` requirements.** Every built-in backend takes
  no constructor arguments (`registry.py` does `cls()`) — keep yours the
  same unless you have a strong reason not to; if you do need
  configuration, read it from environment variables or a well-documented
  file, not constructor parameters (the registry never passes any).

---

## 2. `check_availability()`'s contract

Every backend, regardless of role, returns a `list[dict]` — one entry
**per underlying CLI tool** it depends on (not one entry per backend: xsim
depends on three separate executables, `xvlog`/`xelab`/`xsim`, so its
`check_availability()` returns three entries). This is what
`veriflow doctor` iterates and displays, and what `veriflow db run`/
`veriflow project run` check before starting a run that needs your
backend (`validate_tools`).

Each entry is exactly:

```python
{
    "tool": str,             # the executable name, e.g. "xvlog"
    "available": bool,       # True iff found in PATH and it ran successfully
    "version": str | None,   # first line of version output, or None if unavailable
    "path": str | None,      # shutil.which() result, or None if not in PATH
    "error": str | None,     # human-readable reason when unavailable, else None
}
```

The existing `_check_tool(tool, version_flag="-V")` helper
(`core/backends/_tools.py`) implements this generically — call it once
per executable your backend needs, passing whatever version flag your
tool actually accepts:

```python
def check_availability(self) -> list[dict]:
    return [
        _check_tool("xvlog", version_flag="-version"),
        _check_tool("xelab", version_flag="-version"),
        _check_tool("xsim", version_flag="-version"),
    ]
```

`_check_tool` already handles the two failure modes safely:

- Not in `PATH` at all → `shutil.which()` returns `None`, reported as
  `available=False` with a `"'<tool>' not found in PATH"` error —
  **no subprocess is even attempted**, so an unknown/wrong version flag
  never matters when the tool isn't installed (the common case in CI and
  on most contributors' machines for a commercial tool).
- In `PATH` but the version-flag invocation itself fails (wrong flag,
  crashes, license server unreachable and the tool exits non-zero) →
  caught, reported as `available=False` with the exception message as
  `error`. **This never raises** — `check_availability()` must be safe to
  call unconditionally, including in `veriflow doctor` on a machine that
  has never touched your tool.

If your tool's version flag differs across tools you depend on (real
case: not every Vivado sub-tool necessarily agrees on `-version` vs.
`--version`), call `_check_tool` separately per tool with its own flag —
don't guess one flag for all of them.

---

## 3. Registering the backend

`veriflow/core/backends/registry.py` holds three plain
`dict[str, type[Backend]]` registries — add your class to whichever
one(s) apply:

```python
from veriflow.core.backends.your_tool import YourToolSimulationBackend

_SIMULATION: dict[str, type[SimulationBackend]] = {
    "icarus": IcarusSimulationBackend,
    "xsim": XsimSimulationBackend,
    "your_tool": YourToolSimulationBackend,   # <-- add this line
}
```

Optionally, add a human-readable tool name for `results.json`/
`manifest.yaml` display (defaults to the backend ID itself if omitted —
harmless, just less descriptive):

```python
_SIMULATION_TOOL_NAMES: dict[str, str] = {
    "icarus": "iverilog/vvp",
    "xsim": "xvlog/xelab/xsim",
    "your_tool": "your_tool_cli_name",
}
```

That's the entire integration surface. `veriflow doctor`, `validate_tools`,
`get_simulation_backend("your_tool")`, and every workflow that resolves a
backend by name all read from this same registry — none of them need to
know your backend exists ahead of time.

---

## 4. How a user selects it

Same `execution:` section (or per-stage `pipeline.stages[].backend`
override) that already selects `icarus`/`xsim`/`yosys` — nothing new to
learn:

```yaml
# veriflow.yaml (Project Mode)
execution:
  simulation_backend: your_tool
```

```yaml
# project_config.yaml (Database Mode, database-wide default) or
# tile_config.yaml (per-tile override)
pipeline:
  stages:
    - type: simulation
      backend: your_tool
```

An unregistered name fails fast and clearly — `VF_BACKEND_SIMULATION_UNKNOWN`
(or `_CONNECTIVITY_UNKNOWN`/`_SYNTHESIS_UNKNOWN`) — at config-parse time,
before any tool is even invoked.

---

## 5. Temporary directories and working directory

EDA tools routinely write scratch/work-library state next to wherever
they're invoked from (`.pb` files, `xsim.dir/`, `.Xil/`, `work/` libraries,
license-daemon lock files, ...). **Never let that land in the project
directory.** The established pattern (`core/sim_runner.py`'s
`run_simulation`, mirrored by `XsimSimulationBackend`):

```python
import shutil
import tempfile

tmp_dir = Path(tempfile.mkdtemp(prefix="veriflow_your_tool_"))
try:
    subprocess.run([...], cwd=str(tmp_dir), ...)
    ...
finally:
    shutil.rmtree(tmp_dir, ignore_errors=True)
```

Two real constraints to check for your own tool, illustrated by the
difference between icarus and xsim:

- **icarus's `vvp`** is a self-contained executable with no dependency on
  *where* it was compiled — its run step can freely use a *different* cwd
  than its compile step (specifically `wave_path.parent`, so a
  testbench's `$dumpfile("waves.vcd")` — a relative path — lands exactly
  at the real `wave_path` with no extra step).
- **Vivado's `xelab`** writes its elaborated "snapshot" into
  `xsim.dir/<snapshot_name>/` *relative to xelab's own cwd*, and `xsim`
  looks it up the same way — relative to *its own* cwd. That means all
  three xsim steps (`xvlog`/`xelab`/`xsim`) **must** share one cwd (the
  temp work dir), which means a `$dumpfile("waves.vcd")` call lands
  *there*, not at the real `wave_path`. `XsimSimulationBackend` handles
  this with an explicit copy-back step after `xsim` finishes:

  ```python
  produced_vcd = tmp_dir / "waves.vcd"
  if produced_vcd.is_file():
      shutil.copy2(produced_vcd, wave_path)
  ```

  If your tool has the same "elaborate once, run from the same place"
  constraint, copy the waveform out afterward rather than trying to force
  a different cwd for the run step (it may not even be possible — most
  commercial elaboration flows work exactly like Vivado's here, not
  icarus's).

Either way: **clean up the temp directory in a `finally`**, so a crash or
an early `return` never leaks scratch files. If your tool's own
temp-directory cleanup depends on nothing else still holding an open file
handle (rare, but check your tool's docs for any daemon/server process it
spawns — e.g. some tools start a background simulation kernel process),
make sure that process has actually exited before `rmtree` runs.

### A Windows gotcha that will very likely bite your tool too

Confirmed against a real Vivado 2024.1 install: **always invoke
`shutil.which(tool)`'s *resolved* path, never the bare tool name.**

On Windows, several commercial EDA suites (Vivado's `xvlog`/`xelab`/`xsim`
among them) install each CLI tool as a same-named extensionless file
*alongside* a `"<tool>.bat"` launcher script — the `.bat` is the one that
actually works. `shutil.which("xvlog")` already resolves this correctly
(it does a full `PATHEXT`-aware search, same as `cmd.exe`), returning
`...\xvlog.BAT`. But `subprocess.run(["xvlog", ...])` with the *bare*
name and `shell=False` invokes Windows' `CreateProcess` directly, which
has a loader-level special case for auto-appending `.exe` to a bare name
(why tools that ship a real `.exe` — icarus, yosys — just work) but does
**not** apply the fuller `PATHEXT` resolution that finds `.bat`/`.cmd`
files. The result: `FileNotFoundError` (`[WinError 2]`) even though the
tool is genuinely installed and `shutil.which` just found it moments
earlier.

```python
def _resolve(tool: str) -> str:
    return shutil.which(tool) or tool

subprocess.run([_resolve("xvlog"), "-version"], ...)   # not subprocess.run(["xvlog", ...])
```

This costs nothing on Linux/macOS (`shutil.which`'s result there is
already the same binary the bare name would have found) — there's no
reason not to do this unconditionally, no `platform.system()` branching
needed. Apply it both in `check_availability()` (via `_check_tool`,
which already does this) and in every `run_*` subprocess invocation your
backend makes.

---

## 6. Determining PASS/FAIL deterministically

**Never trust a single signal.** The minimum bar every built-in backend
meets: the underlying tool's own **exit code**. For a tool where exit
code 0 doesn't reliably mean "the design under test is actually correct"
(a real, documented behavior for some commercial simulators, which can
exit 0 even after a runtime fatal error inside the testbench/DUT — the
*process* didn't crash, the *simulation content* did), add a **second
signal**: parse the combined log for the tool's own fatal-error message
format.

`XsimSimulationBackend`'s approach:

```python
_FATAL_LOG_RE = re.compile(r"^\s*(ERROR|FATAL_ERROR|Fatal):", re.IGNORECASE | re.MULTILINE)

status = (
    "COMPLETED"
    if run_result.returncode == 0 and not _FATAL_LOG_RE.search(combined_log)
    else "FAILED"
)
```

This is a **best-effort heuristic** — the exact log message format for
any given commercial tool version may not match a hardcoded pattern
perfectly (Vivado's own format above was not verified against a real
install; adjust the pattern once you have real log samples from your
target tool). The important structural point, not the specific regex:
combine *both* signals (`returncode == 0 AND no-fatal-in-log`), don't
pick just one. Exit-code-only is too permissive for tools with this
quirk; log-parsing-only is fragile against harmless warning text that
happens to contain a similar-looking word.

---

## 7. Full worked example: `XsimSimulationBackend`

The complete, real, currently-shipping implementation
(`veriflow/core/backends/xsim.py`) — copy this file as your starting
point for a new simulation backend, or read it alongside this doc for
a synthesis/connectivity backend (the same principles apply, just with
`run_synthesis`/`run_connectivity`'s signatures instead).

```python
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

_FATAL_LOG_RE = re.compile(r"^\s*(ERROR|FATAL_ERROR|Fatal):", re.IGNORECASE | re.MULTILINE)
_SNAPSHOT_NAME = "veriflow_sim_snapshot"
_VCD_FILENAME = "waves.vcd"


def _resolve(tool: str) -> str:
    """Use shutil.which's own resolved path, not the bare tool name --
    on Windows, Vivado installs xvlog/xelab/xsim as a same-named
    extensionless file alongside a "<tool>.bat" launcher. shutil.which
    already finds the right one (PATHEXT-aware search); subprocess.run
    with the bare name does not (CreateProcess/shell=False only
    auto-resolves ".exe", not ".bat"/".cmd"), and fails with
    FileNotFoundError even though the tool is genuinely installed.
    Confirmed against a real Vivado 2024.1 install. Falls back to the
    bare name when the tool isn't found at all -- that case is meant to
    be caught upstream via check_availability(), not here."""
    return shutil.which(tool) or tool


def _section(step: str, result: subprocess.CompletedProcess) -> str:
    header = f"=== {step} (exit code {result.returncode}) ==="
    body = (result.stdout or "") + (result.stderr or "")
    return f"{header}\n{body}\n"


def _has_fatal_error(log_text: str) -> bool:
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

        tmp_dir = Path(tempfile.mkdtemp(prefix="veriflow_xsim_"))
        log_parts: list[str] = []

        try:
            # 1. xvlog -- compile RTL + TB sources together
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

            # 2. xelab -- elaborate the testbench top into a named snapshot
            elab_cmd = [_resolve("xelab"), tb_top, "-s", _SNAPSHOT_NAME]
            elab_result = subprocess.run(
                elab_cmd, capture_output=True, text=True, cwd=str(tmp_dir),
            )
            log_parts.append(_section("xelab", elab_result))
            if elab_result.returncode != 0:
                sim_log_path.write_text("".join(log_parts), encoding="utf-8")
                return "FAILED", {"sim_time": "", "seed": ""}

            # 3. xsim -- run the elaborated snapshot
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
```

---

## 8. A note on licenses

**VeriFlow does not manage, check out, or otherwise interact with
commercial tool licenses.** That is entirely between your environment and
the tool vendor (license server address, `LM_LICENSE_FILE`, floating vs.
node-locked seats, etc.) — VeriFlow only ever invokes the CLI tool as a
subprocess and reads its exit code and log output, exactly like any other
backend.

This has one direct, documented limitation:
**`check_availability()` cannot generically distinguish "tool is
installed but unlicensed" from "tool is installed and fine"** — a license
checkout failure is just another way for the version-flag subprocess in
`_check_tool` to exit non-zero or hang, which the generic helper already
reports as `available=False` with whatever the tool printed as `error`.
If your tool's license failure message is distinguishable and important
enough to surface specially (e.g. the exact string most users would
search for), you can write a custom `check_availability()` instead of
using `_check_tool` directly — pattern-match the license failure and
return a clearer `error` string, but keep the same
`{"tool", "available", "version", "path", "error"}` dict shape either
way, since `veriflow doctor` and the CLI's tool-validation path both
depend on it.

The same principle applies to `run_simulation`/`run_synthesis`/
`run_connectivity` itself: if a run fails specifically because of a
license checkout failure partway through (not just "tool missing"), that
should still come back as a normal `"FAILED"`/`"FAIL"` result with the
license error visible in the log file — not a crash, and not a status
that looks like a design defect when it wasn't one. Users debugging a
`"FAILED"` run will read the log either way; a license error there is no
different from a syntax error in that respect.
