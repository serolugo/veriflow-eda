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


def _make_db(tmp_path: Path, *, dirname: str = "mydb", interface_name: str | None = None) -> Path:
    from veriflow.commands.init_db import cmd_init

    db_path = tmp_path / dirname
    cmd_init(db_path)
    cfg = {
        "id_prefix": "TST",
        "project_name": "Test DB",
        "repo": "",
        "description": "Test project.",
        "interface_name": interface_name,
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
    # _make_git_repo's project is generic (no interface/tb_sources) -- only
    # synthesis ran, so PARTIAL, not PASS (dev-docs/TRACEABILITY_AUDIT.md
    # Finding #4/#4b) -- still importable, see _IMPORTABLE_STATUSES.
    assert imported_run["status"] == "PARTIAL"

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


# ── 2b. Disallowed git URL scheme (2026-07-19, dev-docs/SECURITY_AUDIT.md #3) ─
# Rejected before any subprocess/network/filesystem work -- confirmed via no
# temp clone directory ever appearing, not just the right exception.


@pytest.mark.parametrize("repo_url", [
    'ext::sh -c "touch /tmp/pwned"',
    "fd::17",
    "ssh://git@github.com/example/repo.git",
    "git://github.com/example/repo.git",
])
def test_import_repo_disallowed_git_url_scheme_rejected(tmp_path, repo_url):
    import tempfile

    db_path = _make_db(tmp_path)
    tmp_before = set(Path(tempfile.gettempdir()).glob("veriflow_import_*"))

    with pytest.raises(VeriFlowError) as exc_info:
        import_repo(repo_url, db_path)
    assert exc_info.value.code == "VF_IMPORT_REPO_URL_SCHEME_NOT_ALLOWED"

    # rejected before ever creating the clone temp dir
    tmp_after = set(Path(tempfile.gettempdir()).glob("veriflow_import_*"))
    assert tmp_after == tmp_before


def test_import_repo_local_path_scheme_still_allowed(tmp_path):
    """The scheme allowlist must not collaterally block the existing,
    legitimate local-path use case (used throughout this file's other
    tests, and real-world testing/offline workflows)."""
    repo_dir = _make_git_repo(tmp_path)
    db_path = _make_db(tmp_path)

    backends = _patched_backends()
    with backends[0], backends[1], backends[2], backends[3]:
        result = import_repo(str(repo_dir), db_path, branch="main")
    assert result["tile_number"] == "0001"


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


# ── 6. Generic repo imported into an interface-requiring database ────────────


def test_import_repo_generic_into_interface_database_blocked_by_default(tmp_path):
    """A generic (no-interface) repo cloned into a database that requires
    an interface is blocked -- inherited from project_import()'s
    VF_IMPORT_GENERIC_TO_INTERFACE_DATABASE check, confirmed end-to-end
    through the whole clone+precheck+import flow."""
    repo_dir = _make_git_repo(tmp_path)
    db_path = _make_db(tmp_path, interface_name="semicolab")

    backends = _patched_backends()
    with backends[0], backends[1], backends[2], backends[3]:
        with pytest.raises(VeriFlowError) as exc_info:
            import_repo(str(repo_dir), db_path, branch="main")

    assert exc_info.value.code == "VF_IMPORT_GENERIC_TO_INTERFACE_DATABASE"
    assert not (db_path / "config" / "tile_0001").exists()


def test_import_repo_generic_into_interface_database_with_force(tmp_path):
    """--force propagates from import_repo() through to project_import()'s
    generic-to-interface-database check, same flag used for the
    duplicate-import guard."""
    repo_dir = _make_git_repo(tmp_path)
    db_path = _make_db(tmp_path, interface_name="semicolab")

    backends = _patched_backends()
    with backends[0], backends[1], backends[2], backends[3]:
        result = import_repo(str(repo_dir), db_path, branch="main", force=True)

    assert result["tile_number"] == "0001"
    assert len(result["warnings"]) == 1
    assert "semicolab" in result["warnings"][0]


# ── External interface.definition consent gate ────────────────────────────────
# dev-docs/SECURITY_AUDIT.md Finding #4: the cloned repo's own veriflow.yaml
# can declare `interface.definition: <third-party URL>` -- resolving it (a
# side effect of just parsing the config, which the precheck does) would
# silently fetch from an origin the caller importing the repo never named.


def _make_git_repo_with_interface_definition(
    tmp_path: Path, *, definition: str, dirname: str = "ifacerepo"
) -> Path:
    """A real local git repo (same recipe as _make_git_repo) whose
    veriflow.yaml declares `interface: {name: fromurl, definition: <definition>}`
    -- either a URL (the attack surface) or a local relative path (the
    always-fine case)."""
    repo_dir = tmp_path / dirname
    (repo_dir / "rtl").mkdir(parents=True)
    (repo_dir / "rtl" / "top.v").write_text(
        "module top(input wire clk); endmodule\n", encoding="utf-8"
    )
    (repo_dir / "veriflow.yaml").write_text(
        "\n".join([
            "design:",
            "  top_module: top",
            "  rtl_sources:",
            "    - rtl/top.v",
            "interface:",
            "  name: fromurl",
            f"  definition: {definition}",
        ]) + "\n",
        encoding="utf-8",
    )
    _git("init", "-q", cwd=repo_dir)
    _git("checkout", "-q", "-b", "main", cwd=repo_dir)
    _git("add", "-A", cwd=repo_dir)
    _git(
        "-c", "user.email=test@test.com", "-c", "user.name=Test",
        "commit", "-q", "-m", "initial", cwd=repo_dir,
    )
    return repo_dir


_IFACE_STUB_V = b"module fromurl(input wire clk); endmodule\n"


def _fake_response(content: bytes):
    resp = MagicMock()
    resp.__enter__ = MagicMock(return_value=resp)
    resp.__exit__ = MagicMock(return_value=False)
    resp.headers = {}
    remaining = bytearray(content)

    def _read(n: int = -1) -> bytes:
        nonlocal remaining
        if n is None or n < 0:
            chunk, remaining = bytes(remaining), bytearray()
            return chunk
        chunk = bytes(remaining[:n])
        del remaining[:n]
        return chunk

    resp.read.side_effect = _read
    return resp


@pytest.fixture
def _clean_interface_registry():
    """A real (non-mocked) import_repo run registers the cloned repo's
    interface.definition into the global, process-wide interface registry,
    pointing at a path inside the temp clone dir that gets deleted once the
    test ends. Undo the registration so later tests (e.g.
    test_interface_profile.py's list_interface_profiles(), which lazily
    re-loads every registered factory) don't blow up on a since-deleted
    path."""
    from veriflow.models.interface_profile import _PROFILE_FACTORIES

    before = set(_PROFILE_FACTORIES)
    yield
    for name in set(_PROFILE_FACTORIES) - before:
        del _PROFILE_FACTORIES[name]


def test_import_repo_uncached_external_interface_url_rejected_by_default(tmp_path):
    """The exact scenario from the audit: the imported repo's own
    veriflow.yaml points interface.definition at a URL the importing user
    never named. Rejected without ever contacting the network -- confirmed
    via urlopen never being called, not just the right error code."""
    from veriflow.models import interface_profile as ip

    repo_dir = _make_git_repo_with_interface_definition(
        tmp_path, definition="https://third-party.example/iface.v"
    )
    db_path = _make_db(tmp_path)

    with patch.object(ip, "VERIFLOW_INTERFACES_CACHE_ROOT", tmp_path / "empty_cache"), \
         patch("urllib.request.urlopen") as mock_urlopen:
        with pytest.raises(VeriFlowError) as exc_info:
            import_repo(str(repo_dir), db_path, branch="main")

    assert exc_info.value.code == "VF_IMPORT_REPO_EXTERNAL_INTERFACE_URL"
    assert "third-party.example" in str(exc_info.value)
    mock_urlopen.assert_not_called()
    # rejected before any tile/config was created
    assert not (db_path / "config" / "tile_0001").exists()


def test_import_repo_allow_external_interface_flag_permits_fetch(tmp_path, _clean_interface_registry):
    """allow_external_interface=True lets the precheck fetch it, same as
    before this guard existed."""
    from veriflow.models import interface_profile as ip

    repo_dir = _make_git_repo_with_interface_definition(
        tmp_path, definition="https://third-party.example/iface.v"
    )
    db_path = _make_db(tmp_path, interface_name="fromurl")

    backends = _patched_backends()
    with patch.object(ip, "VERIFLOW_INTERFACES_CACHE_ROOT", tmp_path / "cache"), \
         patch("urllib.request.urlopen", return_value=_fake_response(_IFACE_STUB_V)), \
         backends[0], backends[1], backends[2], backends[3]:
        result = import_repo(
            str(repo_dir), db_path, branch="main", allow_external_interface=True,
        )

    assert result["tile_number"] == "0001"


def test_import_repo_cached_external_interface_url_not_blocked_without_flag(tmp_path, _clean_interface_registry):
    """A URL already present in the interface cache is never blocked --
    nothing new would be fetched, so there's nothing to consent to."""
    from veriflow.models import interface_profile as ip

    definition = "https://third-party.example/iface.v"
    repo_dir = _make_git_repo_with_interface_definition(tmp_path, definition=definition)
    db_path = _make_db(tmp_path, interface_name="fromurl")

    cache_root = tmp_path / "precached"
    with patch.object(ip, "VERIFLOW_INTERFACES_CACHE_ROOT", cache_root):
        cache_dir = ip._cache_dir_for_url(definition)
        cache_dir.mkdir(parents=True)
        (cache_dir / "interface.v").write_bytes(_IFACE_STUB_V)
        (cache_dir / "source_url.txt").write_text(definition, encoding="utf-8")

        backends = _patched_backends()
        with patch("urllib.request.urlopen") as mock_urlopen, \
             backends[0], backends[1], backends[2], backends[3]:
            result = import_repo(str(repo_dir), db_path, branch="main")

        # already cached -- the real download path is never exercised
        mock_urlopen.assert_not_called()

    assert result["tile_number"] == "0001"


def test_import_repo_local_interface_definition_not_gated(tmp_path, _clean_interface_registry):
    """interface.definition pointing at a local file inside the repo (no
    URL scheme, no third-party origin) must never trigger the gate."""
    repo_dir = _make_git_repo_with_interface_definition(
        tmp_path, definition="./iface.v", dirname="localifacerepo"
    )
    (repo_dir / "iface.v").write_text(
        "module fromurl(input wire clk); endmodule\n", encoding="utf-8"
    )
    _git("add", "-A", cwd=repo_dir)
    _git(
        "-c", "user.email=test@test.com", "-c", "user.name=Test",
        "commit", "-q", "-m", "add iface.v", cwd=repo_dir,
    )
    db_path = _make_db(tmp_path, interface_name="fromurl")

    backends = _patched_backends()
    with patch("urllib.request.urlopen") as mock_urlopen, \
         backends[0], backends[1], backends[2], backends[3]:
        result = import_repo(str(repo_dir), db_path, branch="main")

    mock_urlopen.assert_not_called()
    assert result["tile_number"] == "0001"
