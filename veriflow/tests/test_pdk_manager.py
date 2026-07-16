"""Tests for veriflow.models.pdk_manager -- PDK directory resolution under
VERIFLOW_PDK_ROOT (~/.veriflow/pdks/), consumed by `veriflow pdk` (CLI),
`veriflow doctor`'s [TECHNOLOGIES] section, and SynthesisStage's automatic
liberty resolution.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from veriflow.core import VeriFlowError
from veriflow.models import pdk_manager
from veriflow.models.technology_profile import TechnologyProfile


def _patch_pdk_root(tmp_path: Path):
    return patch.object(pdk_manager, "VERIFLOW_PDK_ROOT", tmp_path)


# ── get_pdk_path ────────────────────────────────────────────────────────────

def test_get_pdk_path_returns_none_when_missing(tmp_path):
    with _patch_pdk_root(tmp_path):
        assert pdk_manager.get_pdk_path("sky130") is None


def test_get_pdk_path_returns_path_when_present(tmp_path):
    (tmp_path / "sky130").mkdir()
    with _patch_pdk_root(tmp_path):
        result = pdk_manager.get_pdk_path("sky130")
    assert result == tmp_path / "sky130"


def test_get_pdk_path_ignores_a_file_with_the_same_name(tmp_path):
    (tmp_path / "sky130").write_text("not a directory", encoding="utf-8")
    with _patch_pdk_root(tmp_path):
        assert pdk_manager.get_pdk_path("sky130") is None


# ── get_liberty_path ─────────────────────────────────────────────────────────

def _fake_technology(**overrides) -> TechnologyProfile:
    base = dict(
        name="sky130",
        pdk_subdir="sky130A",
        liberty_glob="libs.ref/sky130_fd_sc_hd/lib/*.lib",
    )
    base.update(overrides)
    return TechnologyProfile(**base)


def test_get_liberty_path_none_when_pdk_not_installed(tmp_path):
    with _patch_pdk_root(tmp_path), \
         patch("veriflow.models.pdk_manager.get_technology_profile", return_value=_fake_technology()):
        assert pdk_manager.get_liberty_path("sky130") is None


def test_get_liberty_path_none_when_no_liberty_glob(tmp_path):
    (tmp_path / "sky130").mkdir()
    technology = _fake_technology(liberty_glob=None)
    with _patch_pdk_root(tmp_path), \
         patch("veriflow.models.pdk_manager.get_technology_profile", return_value=technology):
        assert pdk_manager.get_liberty_path("sky130") is None


def test_get_liberty_path_none_when_glob_matches_nothing(tmp_path):
    (tmp_path / "sky130" / "sky130A").mkdir(parents=True)
    with _patch_pdk_root(tmp_path), \
         patch("veriflow.models.pdk_manager.get_technology_profile", return_value=_fake_technology()):
        assert pdk_manager.get_liberty_path("sky130") is None


def test_get_liberty_path_returns_matching_file(tmp_path):
    lib_dir = tmp_path / "sky130" / "sky130A" / "libs.ref" / "sky130_fd_sc_hd" / "lib"
    lib_dir.mkdir(parents=True)
    lib_file = lib_dir / "sky130_fd_sc_hd__tt_025C_1v80.lib"
    lib_file.write_text("", encoding="utf-8")
    with _patch_pdk_root(tmp_path), \
         patch("veriflow.models.pdk_manager.get_technology_profile", return_value=_fake_technology()):
        result = pdk_manager.get_liberty_path("sky130")
    assert result == lib_file


def test_get_liberty_path_without_pdk_subdir_searches_pdk_root_directly(tmp_path):
    lib_dir = tmp_path / "ihp130" / "libs.ref" / "sg13g2_stdcell" / "lib"
    lib_dir.mkdir(parents=True)
    lib_file = lib_dir / "sg13g2_stdcell_typ_1p20V_25C.lib"
    lib_file.write_text("", encoding="utf-8")
    technology = _fake_technology(
        name="ihp130", pdk_subdir=None, liberty_glob="libs.ref/sg13g2_stdcell/lib/*.lib"
    )
    with _patch_pdk_root(tmp_path), \
         patch("veriflow.models.pdk_manager.get_technology_profile", return_value=technology):
        result = pdk_manager.get_liberty_path("ihp130")
    assert result == lib_file


def test_get_liberty_path_unknown_technology_raises():
    with pytest.raises(VeriFlowError) as exc_info:
        pdk_manager.get_liberty_path("notapdkname")
    assert exc_info.value.code == "VF_TECHNOLOGY_UNKNOWN"


def test_get_liberty_path_generic_has_no_glob(tmp_path):
    """generic.yaml has no liberty_glob -- always None regardless of what's on disk."""
    with _patch_pdk_root(tmp_path):
        assert pdk_manager.get_liberty_path("generic") is None
