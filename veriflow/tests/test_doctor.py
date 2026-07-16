"""Tests for `veriflow doctor` command."""

from __future__ import annotations

import argparse
import json
from unittest.mock import patch

import pytest

from veriflow.cli import main
from veriflow.commands.doctor import cmd_doctor

# ── stub backend factories ────────────────────────────────────────────────────

def _ok_backend_cls(tool_name: str = "tool"):
    class _Backend:
        def check_availability(self):
            return [{"tool": tool_name, "available": True,
                     "version": "v1.0", "path": f"/bin/{tool_name}", "error": None}]
    return _Backend


def _fail_backend_cls(tool_name: str = "tool"):
    class _Backend:
        def check_availability(self):
            return [{"tool": tool_name, "available": False,
                     "version": None, "path": None,
                     "error": f"{tool_name!r} not found in PATH"}]
    return _Backend


_OK_REGISTRY   = {"fake": _ok_backend_cls("fake")}
_FAIL_REGISTRY = {"fake": _fail_backend_cls("fake")}

# ── A. Exit codes ─────────────────────────────────────────────────────────────

def test_doctor_exits_0_when_all_available(capsys):
    with patch("veriflow.commands.doctor._CONNECTIVITY", _OK_REGISTRY), \
         patch("veriflow.commands.doctor._SIMULATION",   _OK_REGISTRY), \
         patch("veriflow.commands.doctor._SYNTHESIS",    _OK_REGISTRY):
        rc = main(["doctor"])
    assert rc == 0


def test_doctor_exits_1_when_tool_missing(capsys):
    with patch("veriflow.commands.doctor._CONNECTIVITY", _FAIL_REGISTRY), \
         patch("veriflow.commands.doctor._SIMULATION",   _FAIL_REGISTRY), \
         patch("veriflow.commands.doctor._SYNTHESIS",    _FAIL_REGISTRY):
        rc = main(["doctor"])
    assert rc == 1


def test_doctor_exits_1_when_any_category_fails(capsys):
    with patch("veriflow.commands.doctor._CONNECTIVITY", _OK_REGISTRY), \
         patch("veriflow.commands.doctor._SIMULATION",   _OK_REGISTRY), \
         patch("veriflow.commands.doctor._SYNTHESIS",    _FAIL_REGISTRY):
        rc = main(["doctor"])
    assert rc == 1


# ── B. Text output ────────────────────────────────────────────────────────────

def test_doctor_text_shows_ok_marker(capsys):
    with patch("veriflow.commands.doctor._CONNECTIVITY", _OK_REGISTRY), \
         patch("veriflow.commands.doctor._SIMULATION",   _OK_REGISTRY), \
         patch("veriflow.commands.doctor._SYNTHESIS",    _OK_REGISTRY):
        main(["doctor"])
    out = capsys.readouterr().out
    assert "[OK]" in out
    assert "[CONNECTIVITY]" in out
    assert "[SIMULATION]" in out
    assert "[SYNTHESIS]" in out


def test_doctor_text_shows_fail_marker(capsys):
    with patch("veriflow.commands.doctor._CONNECTIVITY", _FAIL_REGISTRY), \
         patch("veriflow.commands.doctor._SIMULATION",   _FAIL_REGISTRY), \
         patch("veriflow.commands.doctor._SYNTHESIS",    _FAIL_REGISTRY):
        main(["doctor"])
    out = capsys.readouterr().out
    assert "[FAIL]" in out


def test_doctor_text_shows_install_docs_pointer_on_failure(capsys):
    with patch("veriflow.commands.doctor._CONNECTIVITY", _OK_REGISTRY), \
         patch("veriflow.commands.doctor._SIMULATION",   _OK_REGISTRY), \
         patch("veriflow.commands.doctor._SYNTHESIS",    _FAIL_REGISTRY):
        main(["doctor"])
    out = capsys.readouterr().out
    assert "docs/INSTALL.md" in out
    assert "installation instructions" in out


def test_doctor_text_omits_install_docs_pointer_when_all_ok(capsys):
    with patch("veriflow.commands.doctor._CONNECTIVITY", _OK_REGISTRY), \
         patch("veriflow.commands.doctor._SIMULATION",   _OK_REGISTRY), \
         patch("veriflow.commands.doctor._SYNTHESIS",    _OK_REGISTRY):
        main(["doctor"])
    out = capsys.readouterr().out
    assert "docs/INSTALL.md" not in out


# ── C. JSON mode ──────────────────────────────────────────────────────────────

def test_doctor_json_all_ok(capsys):
    with patch("veriflow.commands.doctor._CONNECTIVITY", _OK_REGISTRY), \
         patch("veriflow.commands.doctor._SIMULATION",   _OK_REGISTRY), \
         patch("veriflow.commands.doctor._SYNTHESIS",    _OK_REGISTRY):
        rc = main(["--json", "doctor"])
    out = capsys.readouterr().out
    data = json.loads(out)
    assert rc == 0
    assert data["status"] == "OK"
    assert "backends" in data
    assert "connectivity" in data["backends"]
    assert "simulation"   in data["backends"]
    assert "synthesis"    in data["backends"]


def test_doctor_json_with_failure(capsys):
    with patch("veriflow.commands.doctor._CONNECTIVITY", _FAIL_REGISTRY), \
         patch("veriflow.commands.doctor._SIMULATION",   _FAIL_REGISTRY), \
         patch("veriflow.commands.doctor._SYNTHESIS",    _FAIL_REGISTRY):
        rc = main(["--json", "doctor"])
    out = capsys.readouterr().out
    data = json.loads(out)
    assert rc == 1
    assert data["status"] == "FAIL"
    tools = data["backends"]["connectivity"][0]["tools"]
    assert tools[0]["available"] is False


def test_doctor_json_backend_structure(capsys):
    with patch("veriflow.commands.doctor._CONNECTIVITY", _OK_REGISTRY), \
         patch("veriflow.commands.doctor._SIMULATION",   _OK_REGISTRY), \
         patch("veriflow.commands.doctor._SYNTHESIS",    _OK_REGISTRY):
        main(["--json", "doctor"])
    out = capsys.readouterr().out
    data = json.loads(out)
    backend_entry = data["backends"]["connectivity"][0]
    assert "name"  in backend_entry
    assert "tools" in backend_entry
    tool_entry = backend_entry["tools"][0]
    for key in ("tool", "available", "version", "path", "error"):
        assert key in tool_entry


# ── D. Parser ─────────────────────────────────────────────────────────────────

def test_doctor_parses():
    from veriflow.cli import build_parser
    args = build_parser().parse_args(["doctor"])
    assert args.command == "doctor"


# ── E. [TECHNOLOGIES] section ────────────────────────────────────────────────

def test_doctor_technologies_section_lists_all_registered_technologies(tmp_path, capsys):
    with patch("veriflow.commands.doctor._CONNECTIVITY", _OK_REGISTRY), \
         patch("veriflow.commands.doctor._SIMULATION",   _OK_REGISTRY), \
         patch("veriflow.commands.doctor._SYNTHESIS",    _OK_REGISTRY), \
         patch("veriflow.models.pdk_manager.VERIFLOW_PDK_ROOT", tmp_path):
        main(["doctor"])
    out = capsys.readouterr().out
    assert "[TECHNOLOGIES]" in out
    for name in ("generic", "sky130", "gf180", "ihp130"):
        assert name in out


def test_doctor_technologies_missing_pdk_does_not_affect_exit_code(tmp_path, capsys):
    """Missing PDKs are informational -- doctor's exit code is driven solely
    by EDA tool availability, since synthesis still works without a PDK."""
    with patch("veriflow.commands.doctor._CONNECTIVITY", _OK_REGISTRY), \
         patch("veriflow.commands.doctor._SIMULATION",   _OK_REGISTRY), \
         patch("veriflow.commands.doctor._SYNTHESIS",    _OK_REGISTRY), \
         patch("veriflow.models.pdk_manager.VERIFLOW_PDK_ROOT", tmp_path):
        rc = main(["doctor"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "NOT INSTALLED" in out


def test_doctor_technologies_installed_pdk_shows_ok_with_liberty(tmp_path, capsys):
    lib_dir = tmp_path / "sky130" / "sky130A" / "libs.ref" / "sky130_fd_sc_hd" / "lib"
    lib_dir.mkdir(parents=True)
    lib_file = lib_dir / "sky130_fd_sc_hd__tt_025C_1v80.lib"
    lib_file.write_text("", encoding="utf-8")
    with patch("veriflow.commands.doctor._CONNECTIVITY", _OK_REGISTRY), \
         patch("veriflow.commands.doctor._SIMULATION",   _OK_REGISTRY), \
         patch("veriflow.commands.doctor._SYNTHESIS",    _OK_REGISTRY), \
         patch("veriflow.models.pdk_manager.VERIFLOW_PDK_ROOT", tmp_path):
        rc, report = cmd_doctor(argparse.Namespace())
    sky130_entry = next(t for t in report["technologies"] if t["name"] == "sky130")
    assert sky130_entry["status"] == "OK"
    assert sky130_entry["liberty"] == str(lib_file)


def test_doctor_json_includes_technologies(tmp_path, capsys):
    with patch("veriflow.commands.doctor._CONNECTIVITY", _OK_REGISTRY), \
         patch("veriflow.commands.doctor._SIMULATION",   _OK_REGISTRY), \
         patch("veriflow.commands.doctor._SYNTHESIS",    _OK_REGISTRY), \
         patch("veriflow.models.pdk_manager.VERIFLOW_PDK_ROOT", tmp_path):
        rc = main(["--json", "doctor"])
    out = capsys.readouterr().out
    data = json.loads(out)
    assert rc == 0
    names = {t["name"] for t in data["technologies"]}
    assert names == {"generic", "sky130", "gf180", "ihp130"}
    generic_entry = next(t for t in data["technologies"] if t["name"] == "generic")
    assert generic_entry["status"] == "OK"
