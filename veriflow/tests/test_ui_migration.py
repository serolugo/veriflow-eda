"""Tests for silent migration of ~/.semicolab_theme → ~/.veriflow_theme."""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest


def _reload_themes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Return a fresh themes module with home() → tmp_path."""
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    import veriflow.ui.themes as mod
    importlib.reload(mod)
    return mod


class TestThemeFileMigration:
    def test_only_old_file_exists_returns_saved_theme(self, tmp_path, monkeypatch):
        """Old ~/.semicolab_theme present, new absent → preference read from old."""
        (tmp_path / ".semicolab_theme").write_text("dracula", encoding="utf-8")
        mod = _reload_themes(tmp_path, monkeypatch)

        assert mod.load_theme() == "dracula"

    def test_only_old_file_exists_writes_new_file(self, tmp_path, monkeypatch):
        """After migration, ~/.veriflow_theme should contain the preference."""
        (tmp_path / ".semicolab_theme").write_text("nord", encoding="utf-8")
        mod = _reload_themes(tmp_path, monkeypatch)
        mod.load_theme()

        assert (tmp_path / ".veriflow_theme").read_text(encoding="utf-8").strip() == "nord"

    def test_only_old_file_exists_does_not_delete_old(self, tmp_path, monkeypatch):
        """Migration must not remove the old theme file."""
        (tmp_path / ".semicolab_theme").write_text("nord", encoding="utf-8")
        mod = _reload_themes(tmp_path, monkeypatch)
        mod.load_theme()

        assert (tmp_path / ".semicolab_theme").exists()

    def test_neither_file_returns_default_theme(self, tmp_path, monkeypatch):
        """No state files → default theme returned."""
        mod = _reload_themes(tmp_path, monkeypatch)
        assert mod.load_theme() == mod.DEFAULT_THEME

    def test_new_file_exists_returns_new_preference(self, tmp_path, monkeypatch):
        """New ~/.veriflow_theme present → used directly."""
        (tmp_path / ".veriflow_theme").write_text("monokai", encoding="utf-8")
        mod = _reload_themes(tmp_path, monkeypatch)

        assert mod.load_theme() == "monokai"

    def test_new_file_takes_precedence_over_old(self, tmp_path, monkeypatch):
        """New file wins even when old file has a different value."""
        (tmp_path / ".veriflow_theme").write_text("dracula", encoding="utf-8")
        (tmp_path / ".semicolab_theme").write_text("nord", encoding="utf-8")
        mod = _reload_themes(tmp_path, monkeypatch)

        assert mod.load_theme() == "dracula"

    def test_old_file_with_unknown_theme_falls_back_to_default(self, tmp_path, monkeypatch):
        """Old file with an unrecognized theme name → default, not crash."""
        (tmp_path / ".semicolab_theme").write_text("nonexistent-theme", encoding="utf-8")
        mod = _reload_themes(tmp_path, monkeypatch)

        assert mod.load_theme() == mod.DEFAULT_THEME

    def test_save_theme_writes_to_new_file(self, tmp_path, monkeypatch):
        """save_theme() always writes to ~/.veriflow_theme."""
        mod = _reload_themes(tmp_path, monkeypatch)
        mod.save_theme("catppuccin-mocha")

        assert (tmp_path / ".veriflow_theme").read_text(encoding="utf-8").strip() == "catppuccin-mocha"
        assert not (tmp_path / ".semicolab_theme").exists()
