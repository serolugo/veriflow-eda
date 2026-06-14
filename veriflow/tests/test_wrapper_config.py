"""Tests for WrapperConfig.from_dict."""

from __future__ import annotations

import pytest

from veriflow.core import VeriFlowError
from veriflow.models.wrapper_config import WrapperConfig

_VALID = {
    "interface_name": "semicolab",
    "metadata": {"name": "my_ip", "author": "", "description": "", "version": "1.0.0"},
    "design": {
        "top_module": "my_ip",
        "rtl_sources": ["src/my_ip.v"],
    },
    "ports": {"ip_clk": "clk"},
}


def _valid(**overrides) -> dict:
    import copy
    d = copy.deepcopy(_VALID)
    d.update(overrides)
    return d


# ── Valid case ────────────────────────────────────────────────────────────────

def test_from_dict_valid():
    cfg = WrapperConfig.from_dict(_VALID)
    assert cfg.interface_name == "semicolab"
    assert cfg.design.top_module == "my_ip"
    assert cfg.design.rtl_sources == ["src/my_ip.v"]
    assert cfg.ports == {"ip_clk": "clk"}
    assert cfg.wrapper_name == "my_ip_wrapper"


# ── wrapper_name default ──────────────────────────────────────────────────────

def test_wrapper_name_default_when_absent():
    cfg = WrapperConfig.from_dict(_VALID)
    assert cfg.wrapper_name == "my_ip_wrapper"


def test_wrapper_name_explicit_overrides_default():
    d = _valid()
    d["wrapper_name"] = "custom_wrapper"
    cfg = WrapperConfig.from_dict(d)
    assert cfg.wrapper_name == "custom_wrapper"


def test_wrapper_name_empty_string_uses_default():
    d = _valid()
    d["wrapper_name"] = ""
    cfg = WrapperConfig.from_dict(d)
    assert cfg.wrapper_name == "my_ip_wrapper"


# ── interface_name validation ─────────────────────────────────────────────────

def test_missing_interface_name_raises():
    d = _valid()
    del d["interface_name"]
    with pytest.raises(VeriFlowError) as exc_info:
        WrapperConfig.from_dict(d)
    assert exc_info.value.code == "VF_WRAP_INTERFACE_REQUIRED"


def test_null_interface_name_raises():
    d = _valid()
    d["interface_name"] = None
    with pytest.raises(VeriFlowError) as exc_info:
        WrapperConfig.from_dict(d)
    assert exc_info.value.code == "VF_WRAP_INTERFACE_REQUIRED"


def test_empty_interface_name_raises():
    d = _valid()
    d["interface_name"] = "   "
    with pytest.raises(VeriFlowError) as exc_info:
        WrapperConfig.from_dict(d)
    assert exc_info.value.code == "VF_WRAP_INTERFACE_REQUIRED"


def test_unregistered_interface_name_raises():
    d = _valid()
    d["interface_name"] = "does_not_exist"
    with pytest.raises(VeriFlowError) as exc_info:
        WrapperConfig.from_dict(d)
    assert exc_info.value.code == "VF_WRAP_INTERFACE_UNKNOWN"


# ── design.top_module validation ──────────────────────────────────────────────

def test_missing_top_module_raises():
    d = _valid()
    del d["design"]["top_module"]
    with pytest.raises(VeriFlowError) as exc_info:
        WrapperConfig.from_dict(d)
    assert exc_info.value.code == "VF_WRAP_TOP_MODULE_REQUIRED"


def test_empty_top_module_raises():
    d = _valid()
    d["design"]["top_module"] = ""
    with pytest.raises(VeriFlowError) as exc_info:
        WrapperConfig.from_dict(d)
    assert exc_info.value.code == "VF_WRAP_TOP_MODULE_REQUIRED"


# ── design.rtl_sources validation ─────────────────────────────────────────────

def test_missing_rtl_sources_raises():
    d = _valid()
    del d["design"]["rtl_sources"]
    with pytest.raises(VeriFlowError) as exc_info:
        WrapperConfig.from_dict(d)
    assert exc_info.value.code == "VF_WRAP_RTL_SOURCES_EMPTY"


def test_empty_rtl_sources_raises():
    d = _valid()
    d["design"]["rtl_sources"] = []
    with pytest.raises(VeriFlowError) as exc_info:
        WrapperConfig.from_dict(d)
    assert exc_info.value.code == "VF_WRAP_RTL_SOURCES_EMPTY"
