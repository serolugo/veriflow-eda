"""PDK directory management for `veriflow pdk` (zero-configuration PDK
installs -- no manual PDK_ROOT / liberty path environment variables).

VeriFlow keeps installed PDKs under `~/.veriflow/pdks/<technology_name>/`,
one subdirectory per technology (matching the `name:` field in
`veriflow/technologies/<name>.yaml`, not necessarily the PDK's own name).
`get_liberty_path` resolves the actual `.lib` file inside that directory
using the technology profile's `pdk_subdir`/`liberty_glob` fields.
"""

from __future__ import annotations

from pathlib import Path

from veriflow.models.technology_profile import get_technology_profile

VERIFLOW_PDK_ROOT = Path.home() / ".veriflow" / "pdks"


def get_pdk_path(pdk_name: str) -> Path | None:
    """Return VERIFLOW_PDK_ROOT/<pdk_name> if it exists, else None."""
    path = VERIFLOW_PDK_ROOT / pdk_name
    return path if path.is_dir() else None


def get_liberty_path(pdk_name: str) -> Path | None:
    """Resolve the installed liberty (.lib) file for *pdk_name*, or None.

    Returns None when the PDK directory doesn't exist, the technology
    profile declares no `liberty_glob`, or the glob matches nothing. Raises
    VF_TECHNOLOGY_UNKNOWN (via get_technology_profile) if *pdk_name* isn't a
    registered technology.
    """
    technology = get_technology_profile(pdk_name)
    if not technology.liberty_glob:
        return None
    pdk_path = get_pdk_path(pdk_name)
    if pdk_path is None:
        return None
    search_root = (pdk_path / technology.pdk_subdir) if technology.pdk_subdir else pdk_path
    if not search_root.is_dir():
        return None
    matches = sorted(search_root.glob(technology.liberty_glob))
    return matches[0] if matches else None
