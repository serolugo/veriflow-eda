"""Regression tests for testbench scaffold templates.

Guards against the U+2500 box-drawing mojibake previously fixed in
project_config_template.py (dev-docs/SMOKE_TEST_FINDINGS.md).
"""

from __future__ import annotations

from pathlib import Path

import pytest

_PACKAGE_DIR = Path(__file__).parent.parent
_TEMPLATE_PATHS = [
    _PACKAGE_DIR / "interfaces" / "semicolab" / "tb_template.v",
    _PACKAGE_DIR / "template" / "tb_universal_template.v",
]


@pytest.mark.parametrize("path", _TEMPLATE_PATHS, ids=lambda p: p.name)
def test_template_is_pure_ascii(path):
    content = path.read_text(encoding="utf-8")
    content.encode("ascii")  # raises UnicodeEncodeError if any non-ASCII slips in


@pytest.mark.parametrize("path", _TEMPLATE_PATHS, ids=lambda p: p.name)
def test_template_has_no_box_drawing_characters(path):
    content = path.read_text(encoding="utf-8")
    assert "─" not in content
    assert "│" not in content


def test_semicolab_template_dut_instantiation_still_substitutable():
    content = (_PACKAGE_DIR / "interfaces" / "semicolab" / "tb_template.v").read_text(encoding="utf-8")
    assert "/* DUT_MODULE */ DUT (" in content
