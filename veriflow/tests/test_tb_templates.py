"""Regression tests for testbench scaffold templates in veriflow/template/.

Guards against the U+2500 box-drawing mojibake previously fixed in
project_config_template.py (dev-docs/SMOKE_TEST_FINDINGS.md).
"""

from __future__ import annotations

from pathlib import Path

import pytest

_TEMPLATE_DIR = Path(__file__).parent.parent / "template"
_TEMPLATE_NAMES = ["tb_semicolab_template.v", "tb_universal_template.v"]


@pytest.mark.parametrize("name", _TEMPLATE_NAMES)
def test_template_is_pure_ascii(name):
    content = (_TEMPLATE_DIR / name).read_text(encoding="utf-8")
    content.encode("ascii")  # raises UnicodeEncodeError if any non-ASCII slips in


@pytest.mark.parametrize("name", _TEMPLATE_NAMES)
def test_template_has_no_box_drawing_characters(name):
    content = (_TEMPLATE_DIR / name).read_text(encoding="utf-8")
    assert "─" not in content
    assert "│" not in content


def test_semicolab_template_dut_instantiation_still_substitutable():
    content = (_TEMPLATE_DIR / "tb_semicolab_template.v").read_text(encoding="utf-8")
    assert "/* DUT_MODULE */ DUT (" in content
