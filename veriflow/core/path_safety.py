"""Shared path-containment guard for names that come from config/user input
but are meant to stay inside a specific output/working directory.

See dev-docs/SECURITY_AUDIT.md (Findings #1/#2) for the vulnerabilities this
closes: `wrapper_name` (wrapper_config.yaml) and `tile_id` (derived from
`shuttle_name`/`id_prefix`/`id_format`, all user-controlled) were both
interpolated directly into a path (`base_dir / f"{name}.ext"`) with no check
that the result stayed inside `base_dir`. Two things make a naive `/` join
unsafe on its own:

- `Path("a") / "/etc/passwd"` discards `"a"` entirely and returns
  `/etc/passwd` on POSIX -- pathlib's `/` operator treats an absolute right
  operand as a full override, not an error.
- `Path("a") / "../../b"` is accepted just as happily as `Path("a") / "b"`
  -- `..` segments aren't resolved (or rejected) until something calls
  `.resolve()`.

`safe_join()` is the one place that does both: resolve, then verify
containment, before the caller ever touches the filesystem with the result.
"""

from __future__ import annotations

from pathlib import Path

from veriflow.core import VeriFlowError


def safe_join(base_dir: Path, name: str) -> Path:
    """Resolve *name* relative to *base_dir* and verify the result stays
    strictly inside *base_dir* -- rejects absolute paths, `..` segments that
    escape, and symlinks that resolve outside (`Path.resolve()` follows
    symlinks by default, so a symlink inside `base_dir` pointing outside is
    caught by the same containment check as any other escape).

    *base_dir* does not need to exist yet -- `Path.resolve(strict=False)`
    (the default since Python 3.6) normalizes `..`/symlinks without
    requiring the path to be real on disk, which matters for callers
    validating a destination path before creating its parent directory.

    Raises VeriFlowError(VF_UNSAFE_PATH) if *candidate* is not contained in
    *base_dir*.
    """
    base_resolved = base_dir.resolve()
    candidate = (base_dir / name).resolve()
    if not candidate.is_relative_to(base_resolved):
        raise VeriFlowError(
            f"{name!r} resolves outside the expected directory ({base_resolved})",
            code="VF_UNSAFE_PATH",
            details={"name": name, "base_dir": str(base_resolved), "resolved": str(candidate)},
        )
    return candidate
