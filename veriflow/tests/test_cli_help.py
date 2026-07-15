"""Tests for the top-level `veriflow --help` onboarding epilog."""

from __future__ import annotations

from veriflow import __homepage__
from veriflow.cli import build_parser


def test_help_epilog_points_to_project_init():
    parser = build_parser()
    help_text = parser.format_help()
    assert "veriflow project init" in help_text


def test_help_epilog_points_to_homepage():
    parser = build_parser()
    help_text = parser.format_help()
    assert __homepage__ in help_text
