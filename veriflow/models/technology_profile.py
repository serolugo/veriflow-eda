"""Technology profile models and registry.

Built-in technology profiles are loaded from `veriflow/technologies/*.yaml`
at first use -- one file per technology, keyed by its `name:` field. See
`core/synth_runner.py` for how `liberty`/`synth_extra` are applied to the
yosys synthesis script.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from veriflow.core import VeriFlowError

TECHNOLOGIES_DIR = Path(__file__).parent.parent / "technologies"

DEFAULT_TECHNOLOGY_NAME = "generic"


@dataclass
class TechnologyProfile:
    name: str
    description: str = ""
    synthesis_backend: str = "yosys"
    liberty: str | None = None
    synth_extra: list[str] = field(default_factory=list)


def load_technology_profile_from_file(path: Path) -> TechnologyProfile:
    """Load a TechnologyProfile from a `technology.yaml`-shaped file.

    Raises:
        VeriFlowError(VF_TECHNOLOGY_FILE_NOT_FOUND) -- path does not exist
        VeriFlowError(VF_TECHNOLOGY_FILE_INVALID)   -- not a YAML mapping,
            missing the required `name` key, or `synth_extra` isn't a list
    """
    path = Path(path)
    if not path.exists():
        raise VeriFlowError(
            f"Technology definition file not found: {path}",
            code="VF_TECHNOLOGY_FILE_NOT_FOUND",
            details={"path": str(path)},
        )
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or not raw.get("name"):
        raise VeriFlowError(
            f"Technology definition file {path} must be a mapping with at least a 'name' key.",
            code="VF_TECHNOLOGY_FILE_INVALID",
            details={"path": str(path)},
        )

    synth_extra = raw.get("synth_extra") or []
    if not isinstance(synth_extra, list) or not all(isinstance(x, str) for x in synth_extra):
        raise VeriFlowError(
            f"'synth_extra' in {path} must be a list of strings.",
            code="VF_TECHNOLOGY_FILE_INVALID",
            details={"path": str(path), "synth_extra": synth_extra},
        )

    return TechnologyProfile(
        name=raw["name"],
        description=raw.get("description") or "",
        synthesis_backend=raw.get("synthesis_backend") or "yosys",
        liberty=raw.get("liberty"),
        synth_extra=list(synth_extra),
    )


def _load_builtin_technologies() -> dict[str, TechnologyProfile]:
    """Scan TECHNOLOGIES_DIR for `*.yaml` files and load each into the
    registry, keyed by its own `name:` field (not the filename).

    Returns an empty dict if TECHNOLOGIES_DIR doesn't exist (defensive --
    same rationale as `interface_profile._load_builtin_interfaces`).
    """
    registry: dict[str, TechnologyProfile] = {}
    if not TECHNOLOGIES_DIR.is_dir():
        return registry
    for yaml_path in sorted(TECHNOLOGIES_DIR.glob("*.yaml")):
        profile = load_technology_profile_from_file(yaml_path)
        registry[profile.name] = profile
    return registry


_REGISTRY: dict[str, TechnologyProfile] = _load_builtin_technologies()


def default_technology_profile() -> TechnologyProfile:
    return get_technology_profile(DEFAULT_TECHNOLOGY_NAME)


def get_technology_profile(name: str) -> TechnologyProfile:
    try:
        return _REGISTRY[name]
    except KeyError:
        raise VeriFlowError(
            f"Unknown technology profile: {name!r}",
            code="VF_TECHNOLOGY_UNKNOWN",
            details={"name": name, "supported": list(_REGISTRY)},
        )
