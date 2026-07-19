"""Tests for URL-sourced interface definitions (2026-07-19):
`interface.definition:`/`interface_definition:` accepting an http(s):// URL,
resolved through a permanent local cache
(~/.veriflow/interfaces/cache/<sha256(url)>/interface.v) -- same "fetch
once, reuse forever, update explicitly" philosophy as `veriflow pdk`.
"""

from __future__ import annotations

import contextlib
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from veriflow.core import VeriFlowError
from veriflow.models import interface_profile as ip


@contextlib.contextmanager
def _patch_cache_root(tmp_path: Path):
    """VERIFLOW_INTERFACES_CACHE_ROOT is imported by name into both
    `models.interface_profile` (used internally by resolve_interface_definition/
    list_cached_interface_urls/etc.) and `commands.interface` (used directly
    for display) -- patching one does not patch the other, same hazard as
    VERIFLOW_PDK_ROOT (see test_pdk_cli.py's patched_pdk_root)."""
    with patch.object(ip, "VERIFLOW_INTERFACES_CACHE_ROOT", tmp_path), \
         patch("veriflow.commands.interface.VERIFLOW_INTERFACES_CACHE_ROOT", tmp_path):
        yield


@pytest.fixture(autouse=True)
def _cleanup_registered_profiles():
    """Some tests here go through register_interface_profile_from_file --
    remove whatever name(s) got added so other test files aren't affected."""
    before = set(ip._PROFILE_FACTORIES)
    yield
    for name in set(ip._PROFILE_FACTORIES) - before:
        del ip._PROFILE_FACTORIES[name]


def _fake_response(content: bytes):
    resp = MagicMock()
    resp.__enter__ = MagicMock(return_value=resp)
    resp.__exit__ = MagicMock(return_value=False)
    resp.read.return_value = content
    return resp


_STUB_V = (
    b"module fromurl (\n"
    b"    input  wire clk,\n"
    b"    output wire done\n"
    b");\n"
    b"endmodule\n"
)


# ── resolve_interface_definition: URL vs local path ───────────────────────────


def test_resolve_local_path_unaffected(tmp_path):
    """Non-URL definition -- resolved relative to base_dir exactly as
    before this feature, no network/cache logic touched at all."""
    result = ip.resolve_interface_definition("./sub/if.v", tmp_path)
    assert result == (tmp_path / "sub" / "if.v").resolve()


def test_resolve_new_url_downloads_and_caches(tmp_path):
    with _patch_cache_root(tmp_path):
        with patch("urllib.request.urlopen", return_value=_fake_response(_STUB_V)) as mock_open:
            result = ip.resolve_interface_definition("https://example.com/if.v", Path("."))

    assert mock_open.call_count == 1
    assert result.is_file()
    assert result.read_bytes() == _STUB_V
    assert result.name == "interface.v"
    assert (result.parent / "source_url.txt").read_text(encoding="utf-8") == "https://example.com/if.v"


def test_resolve_cached_url_does_not_hit_network(tmp_path):
    with _patch_cache_root(tmp_path):
        with patch("urllib.request.urlopen", return_value=_fake_response(_STUB_V)):
            first = ip.resolve_interface_definition("https://example.com/if.v", Path("."))

        with patch("urllib.request.urlopen") as mock_open_second:
            second = ip.resolve_interface_definition("https://example.com/if.v", Path("."))

    assert mock_open_second.call_count == 0
    assert second == first


def test_resolve_different_urls_get_different_cache_dirs(tmp_path):
    with _patch_cache_root(tmp_path):
        with patch("urllib.request.urlopen", return_value=_fake_response(_STUB_V)):
            a = ip.resolve_interface_definition("https://example.com/a.v", Path("."))
            b = ip.resolve_interface_definition("https://example.com/b.v", Path("."))
    assert a.parent != b.parent


@pytest.mark.parametrize("scheme", ["ftp", "file", "ssh"])
def test_resolve_disallowed_scheme_raises(tmp_path, scheme):
    with _patch_cache_root(tmp_path):
        with pytest.raises(VeriFlowError) as exc_info:
            ip.resolve_interface_definition(f"{scheme}://example.com/if.v", Path("."))
    assert exc_info.value.code == "VF_INTERFACE_URL_SCHEME_NOT_ALLOWED"


def test_resolve_download_failure_raises_fetch_failed(tmp_path):
    import urllib.error

    with _patch_cache_root(tmp_path):
        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("timed out")):
            with pytest.raises(VeriFlowError) as exc_info:
                ip.resolve_interface_definition("https://example.com/if.v", Path("."))
    assert exc_info.value.code == "VF_INTERFACE_URL_FETCH_FAILED"


def test_resolve_download_404_raises_fetch_failed(tmp_path):
    import urllib.error

    http_error = urllib.error.HTTPError(
        "https://example.com/if.v", 404, "Not Found", hdrs=None, fp=None
    )
    with _patch_cache_root(tmp_path):
        with patch("urllib.request.urlopen", side_effect=http_error):
            with pytest.raises(VeriFlowError) as exc_info:
                ip.resolve_interface_definition("https://example.com/if.v", Path("."))
    assert exc_info.value.code == "VF_INTERFACE_URL_FETCH_FAILED"
    assert "404" in str(exc_info.value) or "Not Found" in str(exc_info.value)


def test_resolve_download_failure_leaves_no_partial_cache_entry(tmp_path):
    """A failed download must not leave a cache directory behind that a
    later cache-hit check would mistake for success."""
    import urllib.error

    with _patch_cache_root(tmp_path):
        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("boom")):
            with pytest.raises(VeriFlowError):
                ip.resolve_interface_definition("https://example.com/if.v", Path("."))

        cache_dir = ip._cache_dir_for_url("https://example.com/if.v")
        assert not (cache_dir / "interface.v").exists()


# ── find_cached_interface_by_name / update_cached_interface_url ──────────────


def test_find_cached_interface_by_name_no_cache_dir(tmp_path):
    with _patch_cache_root(tmp_path / "does_not_exist"):
        assert ip.find_cached_interface_by_name("fromurl") is None


def test_find_cached_interface_by_name_matches_module_name(tmp_path):
    with _patch_cache_root(tmp_path):
        with patch("urllib.request.urlopen", return_value=_fake_response(_STUB_V)):
            ip.resolve_interface_definition("https://example.com/if.v", Path("."))
        found = ip.find_cached_interface_by_name("fromurl")
    assert found is not None
    cache_dir, source_url = found
    assert source_url == "https://example.com/if.v"
    assert (cache_dir / "interface.v").is_file()


def test_update_cached_interface_url_force_redownloads(tmp_path):
    updated_content = b"module fromurl(input clk, output done, input extra); endmodule\n"
    with _patch_cache_root(tmp_path):
        with patch("urllib.request.urlopen", return_value=_fake_response(_STUB_V)):
            ip.resolve_interface_definition("https://example.com/if.v", Path("."))

        with patch("urllib.request.urlopen", return_value=_fake_response(updated_content)) as mock_open:
            source_url = ip.update_cached_interface_url("fromurl")

        assert mock_open.call_count == 1
        assert source_url == "https://example.com/if.v"
        cache_dir, _ = ip.find_cached_interface_by_name("fromurl")
        assert cache_dir is not None
        assert (cache_dir / "interface.v").read_bytes() == updated_content


def test_update_cached_interface_url_ignores_existing_cache_hit(tmp_path):
    """update always re-fetches, even though a normal resolve() would have
    been a cache hit needing no network at all."""
    with _patch_cache_root(tmp_path):
        with patch("urllib.request.urlopen", return_value=_fake_response(_STUB_V)):
            ip.resolve_interface_definition("https://example.com/if.v", Path("."))

        with patch("urllib.request.urlopen", return_value=_fake_response(_STUB_V)) as mock_open:
            ip.update_cached_interface_url("fromurl")

    assert mock_open.call_count == 1


def test_update_cached_interface_not_found_raises(tmp_path):
    with _patch_cache_root(tmp_path):
        with pytest.raises(VeriFlowError) as exc_info:
            ip.update_cached_interface_url("never_downloaded")
    assert exc_info.value.code == "VF_INTERFACE_UPDATE_NOT_FOUND"


def test_update_cached_interface_builtin_name_not_found_raises(tmp_path):
    """A built-in profile (e.g. semicolab) has nothing cached -- update
    must not silently succeed or find an unrelated match."""
    with _patch_cache_root(tmp_path):
        with pytest.raises(VeriFlowError) as exc_info:
            ip.update_cached_interface_url("semicolab")
    assert exc_info.value.code == "VF_INTERFACE_UPDATE_NOT_FOUND"


# ── list_cached_interface_urls ────────────────────────────────────────────────


def test_list_cached_interface_urls_empty(tmp_path):
    with _patch_cache_root(tmp_path):
        assert ip.list_cached_interface_urls() == []


def test_list_cached_interface_urls_shows_correct_entries(tmp_path):
    content_a = b"module iface_a(input clk); endmodule\n"
    content_b = b"module iface_b(input clk); endmodule\n"
    with _patch_cache_root(tmp_path):
        with patch("urllib.request.urlopen", return_value=_fake_response(content_a)):
            ip.resolve_interface_definition("https://example.com/a.v", Path("."))
        with patch("urllib.request.urlopen", return_value=_fake_response(content_b)):
            ip.resolve_interface_definition("https://example.com/b.v", Path("."))

        entries = ip.list_cached_interface_urls()

    assert [e["name"] for e in entries] == ["iface_a", "iface_b"]
    assert {e["url"] for e in entries} == {"https://example.com/a.v", "https://example.com/b.v"}
    for e in entries:
        assert e["downloaded_at"] is not None


# ── end-to-end: URL definition through the real config parsers ───────────────


def test_project_mode_interface_definition_url_registers_and_resolves(tmp_path):
    from veriflow.workflows.project_config import ProjectWorkflowConfig

    with _patch_cache_root(tmp_path):
        with patch("urllib.request.urlopen", return_value=_fake_response(_STUB_V)) as mock_open:
            cfg = ProjectWorkflowConfig.from_dict(
                {
                    "design": {"top_module": "top", "rtl_sources": ["rtl/top.v"]},
                    "interface": {"name": "fromurl", "definition": "https://example.com/if.v"},
                },
                root=tmp_path,
            )
    assert mock_open.call_count == 1
    assert cfg.interface.name == "fromurl"

    profile = ip.get_interface_profile("fromurl")
    assert {p.name for p in profile.ports} == {"clk", "done"}


def test_database_mode_interface_definition_url_registers_and_resolves(tmp_path):
    from veriflow.models.project_config import ProjectConfig

    with _patch_cache_root(tmp_path):
        with patch("urllib.request.urlopen", return_value=_fake_response(_STUB_V)) as mock_open:
            config = ProjectConfig.from_dict(
                {
                    "id_prefix": "TST-01",
                    "project_name": "Test",
                    "repo": "",
                    "description": "Test project.",
                    "interface_name": "fromurl",
                    "interface_definition": "https://example.com/if.v",
                },
                root=tmp_path,
            )
    assert mock_open.call_count == 1
    assert config.interface_name == "fromurl"


# ── CLI commands ────────────────────────────────────────────────────────────


def test_cli_interface_list_cached_empty(tmp_path, capsys):
    from veriflow.cli import main

    with _patch_cache_root(tmp_path):
        rc = main(["interface", "list-cached"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "No cached URL-based interface definitions" in out


def test_cli_interface_list_cached_json(tmp_path):
    from veriflow.cli import main

    with _patch_cache_root(tmp_path):
        with patch("urllib.request.urlopen", return_value=_fake_response(_STUB_V)):
            ip.resolve_interface_definition("https://example.com/if.v", Path("."))
        rc = main(["--json", "interface", "list-cached"])
    assert rc == 0


def test_cli_interface_update_dispatches(tmp_path, capsys):
    from veriflow.cli import main

    with _patch_cache_root(tmp_path):
        with patch("urllib.request.urlopen", return_value=_fake_response(_STUB_V)):
            ip.resolve_interface_definition("https://example.com/if.v", Path("."))

        with patch("urllib.request.urlopen", return_value=_fake_response(_STUB_V)) as mock_open:
            rc = main(["interface", "update", "fromurl"])

    assert rc == 0
    assert mock_open.call_count == 1
    out = capsys.readouterr().out
    assert "fromurl" in out


def test_cli_interface_update_not_found_exits_nonzero(tmp_path, capsys):
    from veriflow.cli import main

    with _patch_cache_root(tmp_path):
        rc = main(["interface", "update", "never_downloaded"])
    assert rc != 0
    err = capsys.readouterr().err
    assert "VF_INTERFACE_UPDATE_NOT_FOUND" in err or "never_downloaded" in err
