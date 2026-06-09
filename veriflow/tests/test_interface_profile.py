"""Tests for the interface profile registry APIs."""

from __future__ import annotations

import dataclasses

import pytest

from veriflow.core import VeriFlowError
from veriflow.models import (
    InterfaceProfile,
    default_interface_profile,
    get_interface_profile,
    has_interface_profile,
    list_interface_profile_names,
    list_interface_profiles,
)
from veriflow.models.interface_profile import semicolab_interface_profile


# ── Existing behavior ─────────────────────────────────────────────────────────

def test_get_interface_profile_none_returns_none():
    assert get_interface_profile(None) is None


def test_get_interface_profile_semicolab_returns_profile():
    profile = get_interface_profile("semicolab")
    assert isinstance(profile, InterfaceProfile)
    assert profile.name == "semicolab"
    assert len(profile.ports) == 9


def test_get_interface_profile_unknown_raises():
    with pytest.raises(VeriFlowError) as exc_info:
        get_interface_profile("unknown")
    assert exc_info.value.code == "VF_INTERFACE_UNKNOWN"


def test_get_interface_profile_matches_semicolab_factory():
    assert get_interface_profile("semicolab") == semicolab_interface_profile()


def test_interface_stage_name_is_connectivity():
    from veriflow.core.stages.connectivity import InterfaceStage
    assert InterfaceStage(interface_profile=None).name == "connectivity"


# ── Discovery APIs ────────────────────────────────────────────────────────────

def test_list_interface_profiles_includes_semicolab():
    profiles = list_interface_profiles()
    assert any(p.name == "semicolab" for p in profiles)
    assert all(isinstance(p, InterfaceProfile) for p in profiles)


def test_list_interface_profile_names_includes_semicolab():
    assert "semicolab" in list_interface_profile_names()


def test_has_interface_profile_semicolab_true():
    assert has_interface_profile("semicolab") is True


def test_has_interface_profile_unknown_false():
    assert has_interface_profile("unknown") is False


def test_default_interface_profile_is_none():
    """There is no default interface: projects opt in explicitly via
    interface_name, and an omitted/null value means a generic project."""
    assert default_interface_profile() is None


def test_list_ordering_is_deterministic():
    assert list_interface_profile_names() == list_interface_profile_names()
    assert [p.name for p in list_interface_profiles()] == list_interface_profile_names()


def test_semicolab_profile_has_description():
    profile = get_interface_profile("semicolab")
    assert profile.description


# ── Immutability / registry safety ────────────────────────────────────────────

def test_returned_profiles_are_frozen():
    profile = get_interface_profile("semicolab")
    with pytest.raises(dataclasses.FrozenInstanceError):
        profile.name = "other"


def test_list_interface_profiles_returns_new_list_each_call():
    first = list_interface_profiles()
    second = list_interface_profiles()
    assert first is not second
    first.clear()
    assert [p.name for p in list_interface_profiles()] == [p.name for p in second]


def test_mutating_returned_list_does_not_affect_registry():
    profiles = list_interface_profiles()
    profiles.append("garbage")  # type: ignore[arg-type]
    assert has_interface_profile("semicolab") is True
    assert all(isinstance(p, InterfaceProfile) for p in list_interface_profiles())
