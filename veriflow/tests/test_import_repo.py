"""Regression tests for `veriflow db import-repo` (2026-07-18): cloning a git
repo, running its own `project run` as a live precheck, and importing the
result into a Database Mode database as a new tile.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

from veriflow.api import import_repo
from veriflow.core import VeriFlowError


# ── helpers ───────────────────────────────────────────────────────────────────


def _mock_conn_backend(status="PASS"):
    from veriflow.core.backends.base import ConnectivityBackend
    b = MagicMock(spec=ConnectivityBackend)
    b.run_connectivity.return_value = status
    return b


def _mock_sim_backend(status="COMPLETED"):
    from veriflow.core.backends.base import SimulationBackend
    b = MagicMock(spec=SimulationBackend)
    b.run_simulation.return_value = (status, {})
    return b


def _mock_synth_backend(status="PASS"):
    from veriflow.core.backends.base import SynthesisBackend
    b = MagicMock(spec=SynthesisBackend)
    b.run_synthesis.return_value = (
        status,
        {"cells": "5", "warnings": "0", "errors": "0", "has_latches": False},
    )
    return b


def _patched_backends(*, conn_status="PASS", sim_status="COMPLETED", synth_status="PASS"):
    """Context manager stack patching ProjectWorkflow's backends -- import_repo()
    runs a real `project_run()` internally (not a simulation of one), so its
    precheck needs the same mocked EDA tools as direct `project_import` tests."""
    return (
        patch("veriflow.workflows.project.validate_tools"),
        patch("veriflow.workflows.project.get_connectivity_backend", return_value=_mock_conn_backend(conn_status)),
        patch("veriflow.workflows.project.get_simulation_backend", return_value=_mock_sim_backend(sim_status)),
        patch("veriflow.workflows.project.get_synthesis_backend", return_value=_mock_synth_backend(synth_status)),
    )


def _git(*args, cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


def _make_git_repo(
    tmp_path: Path,
    *,
    dirname: str = "srcrepo",
    top_module: str = "top",
    with_config: bool = True,
    branch: str = "main",
) -> Path:
    """A bare-bones git repo with a committed veriflow.yaml + RTL (unless
    with_config=False), on the given branch. Returns the repo's path
    (usable as a `git clone` URL -- git accepts local paths)."""
    repo_dir = tmp_path / dirname
    (repo_dir / "rtl").mkdir(parents=True)
    (repo_dir / "rtl" / f"{top_module}.v").write_text(
        f"module {top_module}; endmodule\n", encoding="utf-8"
    )
    if with_config:
        (repo_dir / "veriflow.yaml").write_text(
            "\n".join([
                "design:",
                f"  top_module: {top_module}",
                "  rtl_sources:",
                f"    - rtl/{top_module}.v",
            ]) + "\n",
            encoding="utf-8",
        )

    _git("init", "-q", cwd=repo_dir)
    _git("checkout", "-q", "-b", branch, cwd=repo_dir)
    _git("add", "-A", cwd=repo_dir)
    _git("-c", "user.email=test@test.com", "-c", "user.name=Test", "commit", "-q", "-m", "initial", cwd=repo_dir)
    return repo_dir


def _make_db(tmp_path: Path, *, dirname: str = "mydb") -> Path:
    from veriflow.commands.init_db import cmd_init

    db_path = tmp_path / dirname
    cmd_init(db_path)
    cfg = {
        "id_prefix": "TST",
        "project_name": "Test DB",
        "repo": "",
        "description": "Test project.",
        "interface_name": None,
    }
    (db_path / "project_config.yaml").write_text(
        yaml.dump(cfg, default_flow_style=False), encoding="utf-8"
    )
    return db_path


# ── 1. Successful import ──────────────────────────────────────────────────────


def test_import_repo_pass_creates_tile_and_cleans_up_temp_dir(tmp_path):
    import tempfile

    repo_dir = _make_git_repo(tmp_path)
    db_path = _make_db(tmp_path)

    tmp_before = set(Path(tempfile.gettempdir()).glob("veriflow_import_*"))

    backends = _patched_backends()
    with backends[0], backends[1], backends[2], backends[3]:
        result = import_repo(str(repo_dir), db_path, branch="main")

    assert result["tile_number"] == "0001"
    assert result["source_repo"] == str(repo_dir)
    assert result["source_branch"] == "main"

    tile_dir = db_path / "config" / f"tile_{result['tile_number']}"
    assert (tile_dir / "src" / "rtl" / "top.v").is_file()

    imported_run = json.loads((tile_dir / "imported_run.json").read_text(encoding="utf-8"))
    assert imported_run["source_repo"] == str(repo_dir)
    assert imported_run["source_branch"] == "main"
    assert imported_run["status"] == "PASS"

    # No leftover temp clone directory (git marks .git/objects read-only on
    # Windows; a plain `shutil.rmtree(ignore_errors=True)` silently leaves
    # it behind -- confirmed by hitting this for real during manual testing).
    tmp_after = set(Path(tempfile.gettempdir()).glob("veriflow_import_*"))
    assert tmp_after == tmp_before


# ── 2. Clone failure ──────────────────────────────────────────────────────────


def test_import_repo_invalid_url_raises_clone_failed(tmp_path):
    db_path = _make_db(tmp_path)
    bad_repo = tmp_path / "does_not_exist"

    with pytest.raises(VeriFlowError) as exc_info:
        import_repo(str(bad_repo), db_path)
    assert exc_info.value.code == "VF_IMPORT_REPO_CLONE_FAILED"


# ── 3. Missing veriflow.yaml at repo root ─────────────────────────────────────


def test_import_repo_no_config_raises(tmp_path):
    repo_dir = _make_git_repo(tmp_path, dirname="noconfigrepo", with_config=False)
    db_path = _make_db(tmp_path)

    with pytest.raises(VeriFlowError) as exc_info:
        import_repo(str(repo_dir), db_path)
    assert exc_info.value.code == "VF_IMPORT_REPO_NO_CONFIG"
    assert "veriflow.yaml" in str(exc_info.value)


# ── 4. Precheck failure ───────────────────────────────────────────────────────


def test_import_repo_precheck_failed_raises_with_run_details(tmp_path):
    repo_dir = _make_git_repo(tmp_path, dirname="failingrepo")
    db_path = _make_db(tmp_path)

    backends = _patched_backends(synth_status="FAIL")
    with backends[0], backends[1], backends[2], backends[3]:
        with pytest.raises(VeriFlowError) as exc_info:
            import_repo(str(repo_dir), db_path)

    assert exc_info.value.code == "VF_IMPORT_REPO_PRECHECK_FAILED"
    assert exc_info.value.details["run_result"]["status"] == "FAIL"

    # No tile should have been created
    assert not (db_path / "config" / "tile_0001").exists()


# ── 5. Duplicate-import guard ─────────────────────────────────────────────────


def test_import_repo_duplicate_without_force_raises(tmp_path):
    repo_dir = _make_git_repo(tmp_path)
    db_path = _make_db(tmp_path)

    backends = _patched_backends()
    with backends[0], backends[1], backends[2], backends[3]:
        first = import_repo(str(repo_dir), db_path, branch="main")

        with pytest.raises(VeriFlowError) as exc_info:
            import_repo(str(repo_dir), db_path, branch="main")

    assert exc_info.value.code == "VF_IMPORT_REPO_ALREADY_IMPORTED"
    assert first["tile_id"] in str(exc_info.value)


def test_import_repo_duplicate_with_force_creates_second_tile(tmp_path):
    repo_dir = _make_git_repo(tmp_path)
    db_path = _make_db(tmp_path)

    backends = _patched_backends()
    with backends[0], backends[1], backends[2], backends[3]:
        first = import_repo(str(repo_dir), db_path, branch="main")
        second = import_repo(str(repo_dir), db_path, branch="main", force=True)

    assert first["tile_number"] == "0001"
    assert second["tile_number"] == "0002"
    assert first["tile_id"] != second["tile_id"]
    # The original tile is untouched, not overwritten
    assert (db_path / "config" / "tile_0001").exists()
    assert (db_path / "config" / "tile_0002").exists()


def test_import_repo_different_branch_is_not_a_duplicate(tmp_path):
    """Same repo, different branch -- not considered a duplicate at all,
    force isn't even needed."""
    repo_dir = _make_git_repo(tmp_path)
    _git("checkout", "-q", "-b", "dev", cwd=repo_dir)
    db_path = _make_db(tmp_path)

    backends = _patched_backends()
    with backends[0], backends[1], backends[2], backends[3]:
        first = import_repo(str(repo_dir), db_path, branch="main")
        second = import_repo(str(repo_dir), db_path, branch="dev")

    assert first["tile_number"] == "0001"
    assert second["tile_number"] == "0002"
