import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

from veriflow.core.log_parser import parse_synth_log

if TYPE_CHECKING:
    from veriflow.models.technology_profile import TechnologyProfile


def run_synthesis(
    rtl_files: list[Path],
    top_module: str,
    synth_log_path: Path,
    technology: "TechnologyProfile | None" = None,
) -> tuple[str, dict]:
    """
    Run Yosys synthesis.
    Returns (result, parsed_dict).
    result is 'PASS' or 'FAIL'.

    technology, when given, may add to the script:
      - `abc -liberty <path>` right after `synth`, when technology.liberty is set
      - each line in technology.synth_extra, appended after that (before check/stat)
    Both are no-ops when unset (the default, matching every built-in
    technology.yaml today -- none vendors a real liberty file yet).
    """
    synth_log_path.parent.mkdir(parents=True, exist_ok=True)

    # Build Yosys script
    read_cmds = "\n".join(f'read_verilog "{f.as_posix()}"' for f in rtl_files)
    script_lines = [
        read_cmds,
        f"hierarchy -check -top {top_module}",
        "synth",
    ]
    if technology and technology.liberty:
        liberty_path = Path(technology.liberty).as_posix()
        script_lines.append(f'abc -liberty "{liberty_path}"')
    if technology and technology.synth_extra:
        script_lines.extend(technology.synth_extra)
    script_lines += ["check", "stat"]
    script = "\n" + "\n".join(script_lines) + "\n"

    result = subprocess.run(
        ["yosys", "-p", script],
        capture_output=True,
        text=True,
    )
    log_content = result.stdout + result.stderr
    synth_log_path.write_text(log_content, encoding="utf-8")

    parsed = parse_synth_log(log_content)

    if result.returncode != 0 or parsed["has_latches"]:
        status = "FAIL"
    else:
        status = "PASS"

    return status, parsed
