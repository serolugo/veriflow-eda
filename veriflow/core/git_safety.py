"""Shared git-clone URL/scheme safety guard.

See dev-docs/SECURITY_AUDIT.md (Finding #3): git supports its own
"transport helpers" -- a URL of the form `<transport>::<address>` (e.g.
`ext::sh -c "some command"`, `fd::17`) makes `git clone` run *local
commands*, not fetch from a remote. Passing an untrusted `repo_url` straight
to `git clone [...] <repo_url>` executes that helper regardless of the
subprocess call itself being safe (list-form, `shell=False` -- no shell is
involved; this isn't shell injection, it's git's own documented feature
being reachable through an unvalidated URL). Restricting the allowed
schemes *before* ever invoking `git` closes this independent of how git
itself parses the value.
"""

from __future__ import annotations

import re

from veriflow.core import VeriFlowError

# Matches either a standard URL scheme (`https://...`) or git's own
# remote-helper syntax (`ext::...`, no `//` at all) -- both must be
# checked, they're different syntaxes for "this isn't a plain local path".
_SCHEME_RE = re.compile(r"^([a-zA-Z][a-zA-Z0-9+.\-]*)(://|::)")

# Deliberately narrow: only what VeriFlow's own documented workflows
# actually need (public/internal http(s) remotes). `ssh://`/`git://`/
# `file://` are not on this list either -- not just the obviously
# dangerous `ext::`/`fd::` helpers -- since nothing in VeriFlow currently
# needs them and an allowlist is safer than trying to enumerate every
# dangerous scheme by name.
_ALLOWED_GIT_URL_SCHEMES = frozenset({"http", "https"})


def validate_git_clone_url(url: str) -> None:
    """Raise VeriFlowError(VF_IMPORT_REPO_URL_SCHEME_NOT_ALLOWED) unless
    *url* is http(s), or has no scheme at all (a local filesystem path,
    absolute or relative -- including a Windows drive path like `C:\\...`,
    which uses a single colon, not `://`/`::`, so it never matches here).
    """
    match = _SCHEME_RE.match(url)
    if match is None:
        return  # no scheme detected -- treated as a local path, allowed

    scheme = match.group(1).lower()
    if scheme not in _ALLOWED_GIT_URL_SCHEMES:
        raise VeriFlowError(
            f"Unsupported git URL scheme {scheme + match.group(2)!r} in {url!r}. "
            "Only http://, https://, or a local filesystem path (no scheme) are allowed.",
            code="VF_IMPORT_REPO_URL_SCHEME_NOT_ALLOWED",
            details={"url": url, "scheme": scheme},
        )
