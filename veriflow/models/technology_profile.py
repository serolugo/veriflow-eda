"""Technology profile models and registry.

Built-in technology profiles are loaded from `veriflow/technologies/*.yaml`
at first use -- one file per technology, keyed by its `name:` field. See
`core/synth_runner.py` for how `liberty`/`synth_extra` are applied to the
yosys synthesis script.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path

import yaml

from veriflow.core import VeriFlowError

TECHNOLOGIES_DIR = Path(__file__).parent.parent / "technologies"

DEFAULT_TECHNOLOGY_NAME = "generic"


_VALID_INSTALL_METHODS = {"volare", "git"}


@dataclass
class TechnologyProfile:
    name: str
    description: str = ""
    synthesis_backend: str = "yosys"
    liberty: str | None = None
    synth_extra: list[str] = field(default_factory=list)
    # PDK installation metadata -- consumed by `veriflow pdk` (models/pdk_manager.py).
    # install_method is None for technologies with no installable PDK (e.g. "generic").
    install_method: str | None = None      # "volare" | "git" | None
    volare_pdk: str | None = None          # PDK name passed to `volare enable --pdk`
    git_url: str | None = None             # repo URL for install_method == "git"
    pdk_subdir: str | None = None          # subdirectory of VERIFLOW_PDK_ROOT/<name>/ holding the PDK tree
    liberty_glob: str | None = None        # glob pattern (rooted at pdk_subdir, or the PDK dir itself) for the liberty file
    install_hint: str | None = None        # human-readable hint shown when the PDK isn't installed
    default_version: str | None = None     # pinned volare version/commit hash passed positionally to `volare enable`


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

    install_method = raw.get("install_method")
    if install_method is not None and install_method not in _VALID_INSTALL_METHODS:
        raise VeriFlowError(
            f"'install_method' in {path} must be one of {sorted(_VALID_INSTALL_METHODS)} or omitted, "
            f"got {install_method!r}.",
            code="VF_TECHNOLOGY_FILE_INVALID",
            details={"path": str(path), "install_method": install_method},
        )

    return TechnologyProfile(
        name=raw["name"],
        description=raw.get("description") or "",
        synthesis_backend=raw.get("synthesis_backend") or "yosys",
        liberty=raw.get("liberty"),
        synth_extra=list(synth_extra),
        install_method=install_method,
        volare_pdk=raw.get("volare_pdk"),
        git_url=raw.get("git_url"),
        pdk_subdir=raw.get("pdk_subdir"),
        liberty_glob=raw.get("liberty_glob"),
        install_hint=raw.get("install_hint"),
        default_version=raw.get("default_version"),
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


def list_technology_profile_names() -> list[str]:
    """Return all registered technology names, in registration order."""
    return list(_REGISTRY)


def register_technology_profile(profile: TechnologyProfile) -> None:
    """Register (or overwrite) a TechnologyProfile in the process-wide registry."""
    _REGISTRY[profile.name] = profile


def load_and_register_technology_profile_from_file(
    path: Path,
    *,
    liberty_root: Path | None = None,
) -> TechnologyProfile:
    """Load a TechnologyProfile from an external `.yaml` file and register it.

    Used for project-supplied technology definitions
    (`technology.definition:` in `veriflow.yaml` /
    `technology_definition:` in `project_config.yaml`) -- mirrors
    `interface_profile.register_interface_profile_from_file`.

    A relative `liberty:` path in the file is resolved against
    *liberty_root* (the directory containing the config that referenced this
    definition) so it doesn't depend on the process's current working
    directory. An already-absolute `liberty:` path is left unchanged.

    Overwrites any existing profile registered under the same name --
    including a built-in one.

    Returns the registered TechnologyProfile.
    """
    profile = load_technology_profile_from_file(Path(path))
    if liberty_root is not None and profile.liberty:
        liberty_path = Path(profile.liberty)
        if not liberty_path.is_absolute():
            profile = replace(profile, liberty=str((Path(liberty_root) / liberty_path).resolve()))
    register_technology_profile(profile)
    return profile
