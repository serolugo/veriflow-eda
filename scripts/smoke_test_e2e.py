"""End-to-end smoke test for VeriFlow -- Project Mode, Database Mode, Wrap,
PDK/doctor, external interfaces, `set` commands, and expected-error paths.

Standalone script (not a pytest suite): reproduces and extends the manual
smoke testing done by hand, so a full pass over the real CLI surface can be
re-run with one command instead of re-typing a dozen commands by hand every
time. Uses real EDA tools (icarus, yosys) against a real temp directory --
no mocked backends -- except where explicitly noted (xsim is intentionally
never invoked, see NOTE below).

NOTE on xsim: this script never selects xsim as an active backend to run
anything through -- it requires Vivado, which isn't guaranteed to be
installed. `stage-backend simulation:xsim` IS exercised, but only as a
config round-trip (set the key, read the YAML back, confirm the value) --
never executed. xsim was validated manually and separately.

Usage:
    python scripts/smoke_test_e2e.py

Exit code 0 if every group passes, 1 otherwise.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import traceback
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from veriflow import api  # noqa: E402
from veriflow.core import VeriFlowError  # noqa: E402


# ── console noise control ───────────────────────────────────────────────────
# VeriFlow's own commands print via a shared Rich console as a side effect
# (print_step/print_done/...). Silenced for the whole script so only this
# script's own [PASS]/[FAIL]/progress lines show -- same technique
# mcp_server.py's main() uses for stdio, applied here for a clean report.

from veriflow.ui.output import console  # noqa: E402

console.quiet = True


# ── tiny progress/result plumbing ───────────────────────────────────────────

_RESULTS: list[tuple[str, bool, str]] = []


def _log(msg: str) -> None:
    print(f"  ... {msg}", flush=True)


def run_group(label: str, fn) -> None:
    """Run one smoke-test group, catch anything, record PASS/FAIL."""
    print(f"\n=== {label} ===", flush=True)
    try:
        fn()
    except AssertionError as exc:
        _RESULTS.append((label, False, f"AssertionError: {exc}"))
        print(f"[FAIL] {label}\n{exc}", flush=True)
    except Exception:
        tb = traceback.format_exc()
        _RESULTS.append((label, False, tb))
        print(f"[FAIL] {label}\n{tb}", flush=True)
    else:
        _RESULTS.append((label, True, ""))
        print(f"[PASS] {label}", flush=True)


# ── Verilog fixtures (written by the script itself, not pre-supplied) ──────

_COUNTER_V = """\
module counter #(parameter WIDTH = 8) (
    input  wire             clk,
    input  wire             rst_n,
    output reg  [WIDTH-1:0] count
);
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n)
            count <= {WIDTH{1'b0}};
        else
            count <= count + 1'b1;
    end
endmodule
"""

_TOP_V = """\
module smoke_top (
    input  wire       clk,
    input  wire       rst_n,
    output wire [7:0] count_out
);
    counter #(.WIDTH(8)) u_counter (
        .clk   (clk),
        .rst_n (rst_n),
        .count (count_out)
    );
endmodule
"""

_WRAP_DUT_V = """\
module wrap_dut (
    input  wire        clk_i,
    input  wire        rst_ni,
    input  wire [15:0] data_i,
    output wire [7:0]  result_o
);
    assign result_o = data_i[7:0];
endmodule
"""

_CUSTOM_IF_V = """\
module smoke_ext_if (
    input  wire       clk,
    input  wire       rst_n,
    input  wire [7:0] data_in,
    output wire [7:0] data_out
);
endmodule
"""

_CUSTOM_IF_DUT_V = """\
module custom_dut (
    input  wire       clk,
    input  wire       rst_n,
    input  wire [7:0] data_in,
    output wire [7:0] data_out
);
    assign data_out = data_in;
endmodule
"""


# ── shared state between groups (dependency order == requested order) ──────

class Ctx:
    env_root: Path
    project_dir: Path
    project_cfg: Path
    wrap_dir: Path
    wrapper_cfg: Path
    wrapper_out_v: Path
    wrapper_dut_v: Path
    wrapper_name: str
    db_dir: Path
    tile_number: str


CTX = Ctx()


# ── 1. Project Mode: init -> run -> set -> generate-readme ─────────────────

def test_project_mode() -> None:
    CTX.project_dir = CTX.env_root / "project"
    CTX.project_dir.mkdir(parents=True)
    (CTX.project_dir / "counter.v").write_text(_COUNTER_V, encoding="utf-8")
    (CTX.project_dir / "top.v").write_text(_TOP_V, encoding="utf-8")
    CTX.project_cfg = CTX.project_dir / "veriflow.yaml"

    _log("project init")
    result = api.project_init(CTX.project_cfg)
    assert CTX.project_cfg.is_file(), "project init did not write veriflow.yaml"
    assert result["config"] == str(CTX.project_cfg)

    _log("editing yaml programmatically (top_module, rtl_sources)")
    api.project_set(CTX.project_cfg, "top-module", "smoke_top")
    api.project_set(CTX.project_cfg, "rtl-sources", "counter.v,top.v")

    _log("project run (no interface -- connectivity/simulation SKIPPED, synthesis only)")
    run_result = api.project_run(CTX.project_cfg)
    # Not every configured stage type ran (no interface/tb_sources here) --
    # PARTIAL, not PASS (dev-docs/TRACEABILITY_AUDIT.md Finding #4/#4b).
    assert run_result["status"] == "PARTIAL", f"expected PARTIAL, got {run_result['status']!r}: {run_result}"
    assert run_result["stages"]["connectivity"]["status"] == "SKIPPED"
    assert run_result["stages"]["simulation"]["status"] == "SKIPPED"
    assert run_result["stages"]["synthesis"]["status"] == "PASS"

    run_dir = CTX.project_dir / run_result["run_dir"]
    results_json = run_dir / "results.json"
    assert results_json.is_file(), f"results.json missing at {results_json}"
    on_disk = json.loads(results_json.read_text(encoding="utf-8"))
    assert on_disk["status"] == "PARTIAL"

    _log("project set interface null / technology generic / pipeline")
    api.project_set(CTX.project_cfg, "interface", "null")
    api.project_set(CTX.project_cfg, "technology", "generic")
    api.project_set(CTX.project_cfg, "pipeline", "connectivity,simulation,synthesis")
    data = _yaml_load(CTX.project_cfg)
    assert data["interface"] is None
    assert data["technology"] == {"name": "generic"}
    assert data["pipeline"] == {
        "stages": [{"type": "connectivity"}, {"type": "simulation"}, {"type": "synthesis"}]
    }

    _log("project generate-readme")
    content = api.generate_readme(CTX.project_cfg)
    assert content.strip(), "generate_readme returned empty content"
    readme_path = CTX.project_dir / "README.md"
    assert readme_path.is_file(), f"README.md not written at {readme_path}"
    assert readme_path.read_text(encoding="utf-8").strip(), "README.md is empty on disk"


# ── 2. Wrap: init -> generate ────────────────────────────────────────────────

def test_wrap() -> None:
    from veriflow.core.wrapper.config_template import render_wrapper_config_yaml
    from veriflow.models.interface_profile import get_interface_profile

    CTX.wrap_dir = CTX.env_root / "wrap"
    CTX.wrap_dir.mkdir(parents=True)
    dut_path = CTX.wrap_dir / "wrap_dut.v"
    dut_path.write_text(_WRAP_DUT_V, encoding="utf-8")

    _log("wrap init --interface semicolab --top wrap_dut.v")
    config = api.wrap_init("semicolab", dut_path)
    assert config["design"]["top_module"] == "wrap_dut"
    CTX.wrapper_name = config["wrapper_name"]

    _log("completing port mapping programmatically")
    config["ports"] = {
        "clk_i": "clk",
        "rst_ni": "arst_n",
        "data_i": "csr_in[15:0]",
        "result_o": "csr_out[7:0]",
    }
    detected_ports = config.pop("detected_ports")
    ip_ports = [(p["name"], p["direction"], p["width"]) for p in detected_ports]
    interface_profile = get_interface_profile("semicolab")

    CTX.wrapper_cfg = CTX.wrap_dir / "wrapper_config.yaml"
    yaml_str = render_wrapper_config_yaml(config, interface_profile, ip_ports)
    CTX.wrapper_cfg.write_text(yaml_str, encoding="utf-8")

    _log("wrap generate")
    result = api.wrap_generate(CTX.wrapper_cfg)
    assert result["status"] == "PASS", f"expected PASS, got {result!r}"

    CTX.wrapper_out_v = CTX.wrap_dir / "wrap_out" / "rtl" / f"{CTX.wrapper_name}.v"
    assert CTX.wrapper_out_v.is_file(), f"wrapper .v not found at {CTX.wrapper_out_v}"
    CTX.wrapper_dut_v = CTX.wrap_dir / "wrap_out" / "rtl" / "wrap_dut.v"
    assert CTX.wrapper_dut_v.is_file(), "original DUT not copied into wrap_out/rtl/"


# ── 3. Database Mode: init -> create-tile -> run -> bump ───────────────────

def test_database_mode() -> None:
    from veriflow.commands.bump_revision import cmd_bump_revision
    from veriflow.commands.bump_version import cmd_bump_version
    from veriflow.commands.create_tile import cmd_create_tile
    from veriflow.commands.init_db import cmd_init
    from veriflow.core.csv_store import get_tile_row

    CTX.db_dir = CTX.env_root / "db"

    _log("db init")
    cmd_init(CTX.db_dir)
    assert (CTX.db_dir / "project_config.yaml").is_file()

    api.db_set(CTX.db_dir, "prefix", "SMK")
    api.db_set(CTX.db_dir, "interface", "semicolab")

    _log("db create-tile")
    tile_info = cmd_create_tile(CTX.db_dir, top_module=CTX.wrapper_name, tile_author="Smoke Test", silent=True)
    CTX.tile_number = tile_info["tile_number"]
    tile_dir = CTX.db_dir / "config" / f"tile_{CTX.tile_number}"
    assert (tile_dir / "tile_config.yaml").is_file()

    _log("completing tile_config.yaml + copying the wrapper's RTL into the tile")
    api.db_tile_set(CTX.db_dir, CTX.tile_number, "author", "Smoke Bot")
    api.db_tile_set(CTX.db_dir, CTX.tile_number, "objective", "smoke test end-to-end run")
    api.db_tile_set(CTX.db_dir, CTX.tile_number, "tags", "smoke")

    rtl_dir = tile_dir / "src" / "rtl"
    shutil.copy2(CTX.wrapper_out_v, rtl_dir / CTX.wrapper_out_v.name)
    shutil.copy2(CTX.wrapper_dut_v, rtl_dir / CTX.wrapper_dut_v.name)

    _log("db run")
    run_result = api.run_tile(CTX.db_dir, CTX.tile_number, non_interactive=True)
    assert run_result["status"] == "PASS", f"expected PASS, got {run_result['status']!r}: {run_result}"

    _log("db list-tiles / list-runs / show-run")
    tiles = api.db_list_tiles(CTX.db_dir)
    assert any(t["tile_number"] == CTX.tile_number for t in tiles), tiles
    runs = api.db_list_runs(CTX.db_dir, CTX.tile_number)
    assert len(runs) == 1, runs
    run_id = runs[0]["run_id"]
    shown = api.db_get_run(CTX.db_dir, CTX.tile_number, run_id)
    assert shown["status"] == "PASS", shown

    _log("db bump-version")
    cmd_bump_version(CTX.db_dir, CTX.tile_number)
    row = get_tile_row(CTX.db_dir / "tile_index.csv", CTX.tile_number)
    assert row["version"] == "02", row
    assert row["revision"] == "01", row

    _log("db bump-revision")
    cmd_bump_revision(CTX.db_dir, CTX.tile_number)
    row = get_tile_row(CTX.db_dir / "tile_index.csv", CTX.tile_number)
    assert row["version"] == "01", row  # reset on revision bump
    assert row["revision"] == "02", row


# ── 4. Project Import: (1)'s project -> (3)'s database ─────────────────────

def test_project_import() -> None:
    _log("project import (generic project -> interface-requiring database, --force)")
    result = api.project_import(CTX.project_cfg, CTX.db_dir, force=True)
    assert "tile_number" in result, result
    imported_tile_dir = CTX.db_dir / "config" / f"tile_{result['tile_number']}"
    assert imported_tile_dir.is_dir(), imported_tile_dir


# ── 5. PDK commands ──────────────────────────────────────────────────────────

def test_pdk_commands() -> None:
    from veriflow.commands.pdk import cmd_pdk_status
    from veriflow.models.pdk_manager import get_pdk_path

    _log("pdk list (api.list_pdks)")
    pdks = api.list_pdks()
    assert isinstance(pdks, list) and pdks, pdks
    names = {p["name"] for p in pdks}
    assert {"generic", "sky130", "gf180", "ihp130"} <= names, names

    _log("pdk status")
    exit_code, status_payload = cmd_pdk_status(argparse.Namespace())
    assert exit_code == 0
    assert status_payload["pdks"], status_payload

    installed = [p for p in pdks if p["status"] == "installed" and p["name"] != "generic"]
    if not installed:
        _log("no PDKs installed besides 'generic' -- skipping 'pdk path' sub-check")
        return

    _log(f"pdk path {installed[0]['name']}")
    path = get_pdk_path(installed[0]["name"])
    assert path is not None and path.is_dir(), path


# ── 6. Doctor ────────────────────────────────────────────────────────────────

def test_doctor() -> None:
    _log("doctor --json (via real CLI subprocess -- exercises CLI JSON output plumbing)")
    proc = subprocess.run(
        [sys.executable, "-m", "veriflow.cli", "--json", "doctor"],
        capture_output=True, text=True, cwd=str(REPO_ROOT),
    )
    assert proc.returncode == 0, f"doctor exited {proc.returncode}\nstdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
    data = json.loads(proc.stdout)
    assert data["status"] == "OK", data

    icarus_conn = next(b for b in data["backends"]["connectivity"] if b["name"] == "icarus")
    assert icarus_conn["available"] is True, icarus_conn
    icarus_sim = next(b for b in data["backends"]["simulation"] if b["name"] == "icarus")
    assert icarus_sim["available"] is True, icarus_sim
    yosys = next(b for b in data["backends"]["synthesis"] if b["name"] == "yosys")
    assert yosys["available"] is True, yosys


# ── 7. External interfaces: custom .v + `definition:` ───────────────────────

def test_external_interfaces() -> None:
    from veriflow.core.yaml_config_editor import set_yaml_nested_keys

    ext_dir = CTX.env_root / "ext_interface"
    ext_dir.mkdir(parents=True)
    (ext_dir / "custom_if.v").write_text(_CUSTOM_IF_V, encoding="utf-8")
    (ext_dir / "dut.v").write_text(_CUSTOM_IF_DUT_V, encoding="utf-8")

    cfg = ext_dir / "veriflow.yaml"
    api.project_init(cfg)
    api.project_set(cfg, "top-module", "custom_dut")
    api.project_set(cfg, "rtl-sources", "dut.v")

    _log("writing interface.definition (external .v, not a registered name)")
    set_yaml_nested_keys(cfg, "interface", {"name": "smoke_ext_if", "definition": "./custom_if.v"})
    data = _yaml_load(cfg)
    assert data["interface"] == {"name": "smoke_ext_if", "definition": "./custom_if.v"}

    _log("project run -- must use the external profile's real port contract")
    result = api.project_run(cfg)
    assert result["interface_name"] == "smoke_ext_if", result
    assert result["stages"]["connectivity"]["status"] == "PASS", result["stages"]["connectivity"]
    # No tb_sources configured -- simulation never ran, so PARTIAL, not
    # PASS (dev-docs/TRACEABILITY_AUDIT.md Finding #4/#4b).
    assert result["status"] == "PARTIAL", result


# ── 8. Set commands: stage-backend / technology-strict round-trip ──────────

def test_set_commands() -> None:
    scratch_dir = CTX.env_root / "set_cmds"
    scratch_dir.mkdir(parents=True)
    cfg = scratch_dir / "veriflow.yaml"
    api.project_init(cfg)

    _log("project set stage-backend simulation:xsim (config round-trip only -- never executed)")
    api.project_set(cfg, "pipeline", "connectivity,simulation,synthesis")
    api.project_set(cfg, "stage-backend", "simulation:xsim")
    data = _yaml_load(cfg)
    stages = {s["type"]: s.get("backend") for s in data["pipeline"]["stages"]}
    assert stages["simulation"] == "xsim", stages
    assert stages.get("connectivity") is None, stages
    assert stages.get("synthesis") is None, stages

    _log("project set technology-strict sky130")
    api.project_set(cfg, "technology-strict", "sky130")
    data = _yaml_load(cfg)
    assert data["technology"] == {"name": "sky130", "require_pdk": True}, data["technology"]

    _log("db set stage-backend connectivity:icarus")
    api.db_set(CTX.db_dir, "stage-backend", "connectivity:icarus")
    db_data = _yaml_load(CTX.db_dir / "project_config.yaml")
    db_stages = {s["type"]: s.get("backend") for s in db_data["pipeline"]["stages"]}
    assert db_stages["connectivity"] == "icarus", db_stages

    _log("db tile set stage-backend synthesis:yosys")
    api.db_tile_set(CTX.db_dir, CTX.tile_number, "stage-backend", "synthesis:yosys")
    tile_cfg = CTX.db_dir / "config" / f"tile_{CTX.tile_number}" / "tile_config.yaml"
    tile_data = _yaml_load(tile_cfg)
    tile_stages = {s["type"]: s.get("backend") for s in tile_data["pipeline"]["stages"]}
    assert tile_stages["synthesis"] == "yosys", tile_stages

    _log("db set technology-strict sky130")
    api.db_set(CTX.db_dir, "technology-strict", "sky130")
    db_data = _yaml_load(CTX.db_dir / "project_config.yaml")
    assert db_data["technology"] == {"name": "sky130", "require_pdk": True}, db_data["technology"]


# ── 9. Expected error handling ──────────────────────────────────────────────

def test_expected_errors() -> None:
    failures: list[str] = []

    _log("project run without veriflow.yaml")
    try:
        api.project_run(CTX.env_root / "does_not_exist" / "veriflow.yaml")
        failures.append("project_run on a missing config did not raise")
    except VeriFlowError as exc:
        if exc.code != "VF_PROJECT_CONFIG_NOT_FOUND":
            failures.append(f"project_run missing-config: expected VF_PROJECT_CONFIG_NOT_FOUND, got {exc.code}")

    _log("wrap generate with a nonexistent config")
    try:
        api.wrap_generate(CTX.env_root / "does_not_exist" / "wrapper_config.yaml")
        failures.append("wrap_generate on a missing config did not raise")
    except VeriFlowError as exc:
        if exc.code != "VF_WRAP_CONFIG_NOT_FOUND":
            failures.append(f"wrap_generate missing-config: expected VF_WRAP_CONFIG_NOT_FOUND, got {exc.code}")

    _log("db import-repo with an invalid URL")
    if shutil.which("git") is None:
        _log("git not found in PATH -- skipping this sub-check")
    else:
        try:
            api.import_repo(str(CTX.env_root / "no_such_repo"), CTX.db_dir)
            failures.append("import_repo with an invalid URL did not raise")
        except VeriFlowError as exc:
            if exc.code != "VF_IMPORT_REPO_CLONE_FAILED":
                failures.append(f"import_repo invalid URL: expected VF_IMPORT_REPO_CLONE_FAILED, got {exc.code}")

    _log("project_import generic -> interface-requiring database, no --force")
    try:
        api.project_import(CTX.project_cfg, CTX.db_dir, force=False)
        failures.append("project_import generic->interface-requiring db without --force did not raise")
    except VeriFlowError as exc:
        if exc.code != "VF_IMPORT_GENERIC_TO_INTERFACE_DATABASE":
            failures.append(
                f"project_import no-force: expected VF_IMPORT_GENERIC_TO_INTERFACE_DATABASE, got {exc.code}"
            )

    assert not failures, "\n".join(failures)


# ── helpers ──────────────────────────────────────────────────────────────────

def _yaml_load(path: Path) -> dict:
    import yaml

    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


# ── main ─────────────────────────────────────────────────────────────────────

_GROUPS = [
    ("Project Mode: init -> run -> set -> generate-readme", test_project_mode),
    ("Wrap: init -> generate", test_wrap),
    ("Database Mode: init -> create-tile -> run -> bump", test_database_mode),
    ("Project Import", test_project_import),
    ("PDK commands", test_pdk_commands),
    ("Doctor", test_doctor),
    ("External interfaces", test_external_interfaces),
    ("Set commands (stage-backend, technology-strict)", test_set_commands),
    ("Expected error handling", test_expected_errors),
]


def main() -> int:
    CTX.env_root = Path(tempfile.mkdtemp(prefix="veriflow_smoke_"))
    print(f"Smoke test environment: {CTX.env_root}")

    try:
        for label, fn in _GROUPS:
            run_group(label, fn)
    finally:
        shutil.rmtree(CTX.env_root, ignore_errors=True)
        console.quiet = False

    print("\n=== Smoke Test Summary ===")
    passed = 0
    for label, ok, detail in _RESULTS:
        tag = "PASS" if ok else "FAIL"
        print(f"[{tag}] {label}")
        if not ok:
            indented = "\n".join(f"      {line}" for line in detail.splitlines())
            print(indented)
        passed += 1 if ok else 0

    total = len(_RESULTS)
    print(f"Total: {passed}/{total} passed")

    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
