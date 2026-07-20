"""Tests for veriflow.core.git_safety.validate_git_clone_url() --
dev-docs/SECURITY_AUDIT.md Finding #3: git's own `<transport>::<address>`
remote-helper syntax (`ext::`, `fd::`, ...) runs local commands when used as
a clone URL, reachable through any unvalidated `git clone <url>` call.
"""

from __future__ import annotations

import pytest

from veriflow.core import VeriFlowError
from veriflow.core.git_safety import validate_git_clone_url


@pytest.mark.parametrize("url", [
    "https://github.com/example/repo.git",
    "https://internal.example/repo",
    "http://internal.example/repo.git",  # explicitly allowed for internal/self-hosted mirrors
])
def test_allowed_schemes_pass(url):
    validate_git_clone_url(url)  # must not raise


@pytest.mark.parametrize("path", [
    "C:/Users/dev/local/repo",
    "/home/dev/local/repo",
    "../relative/repo",
    "./repo",
    "repo",
    "",
])
def test_local_paths_without_scheme_pass(path):
    validate_git_clone_url(path)  # must not raise -- git accepts these too


@pytest.mark.parametrize("url", [
    'ext::sh -c "touch /tmp/pwned"',
    "ext::sh -c 'touch pwned'",
    "fd::17",
    "fd::0,1",
])
def test_git_remote_helper_syntax_rejected(url):
    with pytest.raises(VeriFlowError) as exc_info:
        validate_git_clone_url(url)
    assert exc_info.value.code == "VF_IMPORT_REPO_URL_SCHEME_NOT_ALLOWED"


@pytest.mark.parametrize("url", [
    "ssh://git@github.com/example/repo.git",
    "git://github.com/example/repo.git",
    "file:///etc/passwd",
    "ftp://example.com/repo",
])
def test_other_unlisted_schemes_rejected(url):
    """Not just the obviously dangerous ext::/fd:: -- anything outside the
    explicit http(s) allowlist is rejected, including schemes that aren't
    remote-helper syntax at all (ssh://, git://, file://)."""
    with pytest.raises(VeriFlowError) as exc_info:
        validate_git_clone_url(url)
    assert exc_info.value.code == "VF_IMPORT_REPO_URL_SCHEME_NOT_ALLOWED"


def test_scheme_case_insensitive():
    with pytest.raises(VeriFlowError) as exc_info:
        validate_git_clone_url("EXT::sh -c evil")
    assert exc_info.value.code == "VF_IMPORT_REPO_URL_SCHEME_NOT_ALLOWED"


def test_error_details_include_url_and_scheme():
    with pytest.raises(VeriFlowError) as exc_info:
        validate_git_clone_url("ext::sh -c evil")
    assert exc_info.value.details["scheme"] == "ext"
    assert "ext::sh -c evil" == exc_info.value.details["url"]
