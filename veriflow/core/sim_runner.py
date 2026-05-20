import re
import subprocess
import tempfile
from pathlib import Path

from veriflow.core.log_parser import parse_sim_log

USER_TEST_PLACEHOLDER   = "/* USER_TEST */"
MODULE_INST_PLACEHOLDER = "/* MODULE_INSTANTIATION */"

_DUMPFILE_INJECT = """\

initial begin
    $dumpfile("waves.vcd");
    $dumpvars(0, tb);
end
"""


def _build_dut_inst(top_module: str) -> str:
    return f"""{top_module} DUT (
    .clk       (clk),
    .arst_n    (arst_n),
    .csr_in    (csr_in),
    .data_reg_a(data_reg_a),
    .data_reg_b(data_reg_b),
    .data_reg_c(data_reg_c),
    .csr_out   (csr_out),
    .csr_in_re (csr_in_re),
    .csr_out_we(csr_out_we)
);"""


def _ensure_dumpfile(content: str) -> str:
    """
    If the TB content does not already contain a $dumpfile call,
    inject one right after the first 'module <name>;' or 'module <name> (...);' line.
    This ensures waveforms are always generated regardless of what the user wrote.
    """
    if "$dumpfile" in content:
        return content

    # Find end of module declaration (after the semicolon closing it)
    m = re.search(r"(module\s+\w+[^;]*;)", content)
    if m:
        insert_pos = m.end()
        return content[:insert_pos] + _DUMPFILE_INJECT + content[insert_pos:]

    # Fallback: prepend at the start of the file
    return _DUMPFILE_INJECT + content


def _read_user_test(tb_files: list[Path]) -> str:
    """
    Collect user test code from all files in src/tb/.
    Skips tb_tasks.v (already included via `include in the wrapper).
    Strips timescale, module declarations, and endmodule — only keeps
    the raw statements inside // USER TEST STARTS HERE // markers if present,
    otherwise includes the full file content.
    """
    parts = []
    for f in tb_files:
        # Skip tb_tasks.v — already included via `include in tb_tile.v
        if f.name == "tb_tasks.v":
            continue
        content = f.read_text(encoding="utf-8")

        # If file has USER TEST markers, extract only what's between them
        m = re.search(
            r"//\s*USER TEST STARTS HERE\s*//(.*)//\s*USER TEST ENDS HERE\s*//",
            content,
            re.DOTALL,
        )
        if m:
            parts.append(m.group(1))
        else:
            # Strip timescale, module/endmodule wrappers if present
            content = re.sub(r"`timescale[^\n]*\n", "", content)
            content = re.sub(r"\bmodule\s+\w+\s*;", "", content)
            content = re.sub(r"\bendmodule\b", "", content)
            parts.append(content)

    return "\n".join(parts).strip()


def _inject_tb(
    tb_base_path: Path,
    top_module: str,
    tb_files: list[Path],
) -> Path:
    """
    Read tb_base.v (tb_tile.v in semicolab mode) and inject:
      1. DUT instantiation at /* MODULE_INSTANTIATION */
      2. User test code at /* USER_TEST */
    Write result to a temporary file and return its path.
    """
    content = tb_base_path.read_text(encoding="utf-8")

    # Inject DUT
    content = content.replace(MODULE_INST_PLACEHOLDER, _build_dut_inst(top_module))

    # Extract user test from tb_tile.v markers (same file as the wrapper)
    # This is the primary source — user writes test directly in tb_tile.v
    user_test = _read_user_test([tb_base_path])
    content = content.replace(USER_TEST_PLACEHOLDER, user_test)

    tmp = tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".v",
        delete=False,
        encoding="utf-8",
    )
    tmp.write(content)
    tmp.close()
    return Path(tmp.name)


def _prepare_universal_tb(tb_files: list[Path]) -> Path:
    """
    For universal mode: read tb_tile.v, ensure $dumpfile is present,
    write to a temporary file and return its path.
    """
    if not tb_files:
        raise ValueError("No TB files found for universal mode simulation")

    # Use the first tb file as the main TB
    content = tb_files[0].read_text(encoding="utf-8")
    content = _ensure_dumpfile(content)

    tmp = tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".v",
        delete=False,
        encoding="utf-8",
    )
    tmp.write(content)
    tmp.close()
    return Path(tmp.name)


def run_connectivity_check(
    rtl_files: list[Path],
    tb_base_path: Path,
    tb_tasks_path: Path,
    top_module: str,
    log_path: Path,
) -> str:
    """
    Run iverilog connectivity check.
    Returns 'PASS' or 'FAIL'.
    """
    log_path.parent.mkdir(parents=True, exist_ok=True)

    # Connectivity check uses no user TB files — just DUT injection
    tmp_tb = _inject_tb(tb_base_path, top_module, tb_files=[])

    try:
        include_dir = tb_tasks_path.parent
        cmd = (
            ["iverilog", "-o", "/dev/null" if _is_unix() else "NUL"]
            + ["-I", include_dir.as_posix()]
            + [f.as_posix() for f in rtl_files]
            + [Path(tmp_tb).as_posix()]
        )
        result = subprocess.run(cmd, capture_output=True, text=True)
        log_content = result.stdout + result.stderr
        log_path.write_text(log_content, encoding="utf-8")
        return "PASS" if result.returncode == 0 else "FAIL"
    finally:
        Path(tmp_tb).unlink(missing_ok=True)


def run_simulation(
    rtl_files: list[Path],
    tb_files: list[Path],
    tb_base_path,
    tb_tasks_path,
    top_module: str,
    sim_log_path: Path,
    wave_path: Path,
    semicolab: bool = True,
) -> tuple[str, dict]:
    """
    Compile and run simulation using iverilog/vvp.
    Returns (result, parsed_log_dict).
    result is 'COMPLETED' or 'FAILED'.
    """
    sim_log_path.parent.mkdir(parents=True, exist_ok=True)
    wave_path.parent.mkdir(parents=True, exist_ok=True)

    if semicolab:
        # Semicolab mode: inject DUT + user test into tb_tile.v (tb_base)
        # Exclude tb_tasks.v from tb_files — it is already included via `include in the wrapper
        user_tb_files = [f for f in tb_files if f.name not in ("tb_tasks.v", "tb_tile.v")]
        tmp_tb = _inject_tb(tb_base_path, top_module, tb_files=user_tb_files)
        include_dir = tb_tasks_path.parent if tb_tasks_path else None
    else:
        # Universal mode: ensure $dumpfile is present, compile directly
        tmp_tb = _prepare_universal_tb(tb_files)
        include_dir = None

    tmp_dir = Path(tempfile.mkdtemp())
    compiled = tmp_dir / "sim.out"

    try:
        compile_cmd = (
            ["iverilog", "-o", compiled.as_posix()]
            + (["-I", include_dir.as_posix()] if include_dir else [])
            + [f.as_posix() for f in rtl_files]
            + [Path(tmp_tb).as_posix()]
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
        Path(tmp_tb).unlink(missing_ok=True)
        import shutil
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
    import shutil

    # Docker — always use Surfer WASM
    if os.environ.get("SEMICOLAB_DOCKER"):
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
