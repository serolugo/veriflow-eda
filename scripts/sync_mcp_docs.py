"""
Copy the subset of docs/ exposed as MCP resources into veriflow/mcp_docs/.

docs/ lives outside the veriflow/ package directory, so it isn't included in
a `pip install veriflow-eda` wheel (setup.py's package_data only covers
files inside veriflow/). veriflow/mcp_docs/ is a packaged, flat-named copy
of exactly the files veriflow/mcp_server.py's @mcp.resource functions read
via importlib.resources -- docs/ remains the single source of truth; this
script is the only thing that writes to veriflow/mcp_docs/.

Run after editing any of the source files below. test_mcp_resources.py
fails if the two ever diverge, as a reminder to re-run this.

    python scripts/sync_mcp_docs.py
"""

from __future__ import annotations

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
DEST = ROOT / "veriflow" / "mcp_docs"

# (source path relative to docs/, destination filename in veriflow/mcp_docs/)
FILES = [
    ("MANUAL.md", "manual.md"),
    ("QUICKREF.md", "quickref.md"),
    ("PROJECT_CONFIG.md", "project-config.md"),
    ("INSTALL.md", "install.md"),
    ("CUSTOM_BACKENDS.md", "custom-backends.md"),
    ("user-guide/wrap.md", "wrap.md"),
    ("user-guide/doctor.md", "doctor.md"),
]


def sync() -> list[Path]:
    DEST.mkdir(parents=True, exist_ok=True)
    written = []
    for src_rel, dest_name in FILES:
        src = DOCS / src_rel
        dest = DEST / dest_name
        shutil.copy2(src, dest)
        written.append(dest)
    return written


if __name__ == "__main__":
    for path in sync():
        print(f"wrote {path.relative_to(ROOT)}")
