import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from veriflow.core.log_parser import parse_sim_log


def _build_interface_check_wrapper(top_module: str, interface_profile: object) -> str:
    """Generate a minimal Verilog elaboration wrapper from an InterfaceProfile.

    The wrapper declares one signal per port using the profile's declared width
    and direction, then instantiates top_module with named port connections.
    It contains no clock behaviour, reset, tasks, stimulus, assertions or user
    test content.

    Diagnostic limitation: Verilog elaboration backends (including Icarus
    Verilog) report port-not-found errors when a declared port name is absent
    from the DUT, and typically emit width-mismatch warnings when a connected
    signal has a different width.  However, they do NOT flag DUT ports that are
    absent from the profile — those remain unconnected without an error.
    The profile therefore acts as a declared set of connections, not a
    mandatory complete enumeration of the DUT's interface.
    """
    lines = ["module interface_check_wrapper;"]
    for port in interface_profile.ports:
        sig_type = "reg" if port.direction == "input" else "wire"
        if port.width == 1:
            lines.append(f"  {sig_type} {port.name};")
        else:
            lines.append(f"  {sig_type} [{port.width - 1}:0] {port.name};")
    lines.append(f"  {top_module} DUT (")
    port_lines = [f"    .{p.name}({p.name})" for p in interface_profile.ports]
    lines.append(",\n".join(port_lines))
    lines.append("  );")
    lines.append("endmodule")
    return "\n".join(lines) + "\n"


def run_connectivity_check(
    rtl_files: list[Path],
    interface_profile: object,
    top_module: str,
    log_path: Path,
) -> str:
    """Run iverilog interface/connectivity check using a generated elaboration wrapper.

    Compiles only the RTL sources and a minimal wrapper generated from
    interface_profile.  Does not read or compile user testbench files.
    Returns 'PASS' or 'FAIL'.
    """
    log_path.parent.mkdir(parents=True, exist_ok=True)

    wrapper_content = _build_interface_check_wrapper(top_module, interface_profile)
    tmp = tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".v",
        delete=False,
        encoding="utf-8",
    )
    tmp.write(wrapper_content)
    tmp.close()
    tmp_path = Path(tmp.name)

    try:
        cmd = (
            ["iverilog", "-o", "/dev/null" if _is_unix() else "NUL"]
            + [f.as_posix() for f in rtl_files]
            + [tmp_path.as_posix()]
        )
        result = subprocess.run(cmd, capture_output=True, text=True)
        log_content = result.stdout + result.stderr
        log_path.write_text(log_content, encoding="utf-8")
        return "PASS" if result.returncode == 0 else "FAIL"
    finally:
        tmp_path.unlink(missing_ok=True)


def run_simulation(
    rtl_files: list[Path],
    tb_files: list[Path],
    tb_top: str,
    sim_log_path: Path,
    wave_path: Path,
) -> tuple[str, dict]:
    """Compile and run simulation using iverilog/vvp.

    Compiles all rtl_files and tb_files together.  The testbench top module is
    selected explicitly via -s tb_top.  No injection, no temp TB sources, no
    include paths for hidden helpers.

    Returns (status, parsed_log_dict) where status is 'COMPLETED' or 'FAILED'.
    """
    sim_log_path.parent.mkdir(parents=True, exist_ok=True)
    wave_path.parent.mkdir(parents=True, exist_ok=True)

    tmp_dir = Path(tempfile.mkdtemp())
    compiled = tmp_dir / "sim.out"

    try:
        compile_cmd = (
            ["iverilog", "-o", compiled.as_posix(), "-s", tb_top]
            + [f.as_posix() for f in rtl_files]
            + [f.as_posix() for f in tb_files]
        )
        compile_result = subprocess.run(compile_cmd, capture_output=True, text=True)
        compile_log = compile_result.stdout + compile_result.stderr

        if compile_result.returncode != 0:
            sim_log_path.write_text(compile_log, encoding="utf-8")
            return "FAILED", {"sim_time": "", "seed": ""}

        # Run vvp from wave dir so $dumpfile("waves.vcd") lands there
        run_result = subprocess.run(
            ["vvp", compiled.as_posix()],
            capture_output=True,
            text=True,
            cwd=str(wave_path.parent),
        )
        run_log = compile_log + run_result.stdout + run_result.stderr
        sim_log_path.write_text(run_log, encoding="utf-8")

        parsed = parse_sim_log(run_log)
        status = "COMPLETED" if run_result.returncode == 0 else "FAILED"
        return status, parsed
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def open_surfer(wave_path: Path) -> None:
    """In TileBench (Docker) mode: open Surfer WASM with the VCD preloaded."""
    import webbrowser
    from urllib.parse import quote

    try:
        rel = wave_path.resolve().relative_to(Path("/workspace"))
        vcd_url = f"http://localhost:7681/files/{rel.as_posix()}"
        surfer_url = f"http://localhost:7681/?load_url={quote(vcd_url, safe='')}"
    except ValueError:
        # VCD not under /workspace — open Surfer without preloading
        surfer_url = "http://localhost:7681"
        vcd_url = None

    print()
    print("✓ Waveform ready.")
    print(f"  Open in browser → {surfer_url}")
    if vcd_url is None:
        print("  (Could not resolve VCD path — load the file manually in Surfer)")

    try:
        webbrowser.open(surfer_url)
    except Exception:
        pass


def launch_waves(wave_path: Path) -> None:
    """Launch waveform viewer for the given VCD file (non-blocking).

    Priority:
      1. Docker → Surfer WASM (browser URL)
      2. Local  → Surfer native binary if found in PATH
    """
    import os
    import platform

    # Docker — always use Surfer WASM
    # SEMICOLAB_DOCKER is deprecated; VERIFLOW_DOCKER is the current name
    if os.environ.get("VERIFLOW_DOCKER") or os.environ.get("SEMICOLAB_DOCKER"):
        open_surfer(wave_path)
        return

    # Windows: no_window evita el flash de consola
    _no_window = {"creationflags": subprocess.CREATE_NO_WINDOW} if platform.system() == "Windows" else {}

    # Local — try Surfer native first
    surfer_path = shutil.which("surfer")
    if surfer_path:
        subprocess.Popen(
            [surfer_path, str(wave_path)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            **_no_window,
        )
        return

    print("[waves] Surfer not found in PATH. Install Surfer: https://surfer-project.org")


def _is_unix() -> bool:
    import platform
    return platform.system() != "Windows"
