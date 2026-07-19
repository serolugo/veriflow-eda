"""`veriflow project set` / `veriflow db set` / `veriflow db tile set` --
modify a config file's fields from the CLI (or `veriflow.api`) without
hand-editing YAML. Especially useful for AI agents that need to configure
a project/tile without a text editor.

Each `*_set_config` function here is reused directly by `veriflow/api.py`
(`project_set`/`db_set`/`db_tile_set`) -- the CLI command functions
(`cmd_*`) are thin wrappers that parse `args` and print a confirmation.
"""

from __future__ import annotations

import argparse
import warnings
from pathlib import Path

import yaml

from veriflow.core import VeriFlowError
from veriflow.core.backends.registry import _CONNECTIVITY, _SIMULATION, _SYNTHESIS
from veriflow.core.yaml_config_editor import set_yaml_key, set_yaml_nested_keys, set_yaml_pipeline
from veriflow.models.interface_profile import has_interface_profile
from veriflow.models.pipeline_config import DEFAULT_PIPELINE, PipelineConfig, VALID_STAGE_TYPES
from veriflow.models.technology_profile import get_technology_profile
from veriflow.ui.output import print_done

_PROJECT_SET_KEYS = (
    "interface", "technology", "technology-strict", "require-pdk", "top-module", "pipeline",
    "stage-backend", "runs-dir", "rtl-sources", "tb-sources", "tb-top", "name", "author",
    "description", "version",
)
_DB_SET_KEYS = (
    "interface", "technology", "technology-strict", "require-pdk", "id-format", "prefix",
    "shuttle", "pipeline", "stage-backend",
)
_DB_TILE_SET_KEYS = (
    "top-module", "tb-top", "name", "author", "description", "tags", "objective", "pipeline",
    "stage-backend", "require-pdk",
)

# stage type -> registry dict of backend_name -> backend class, used to
# validate `stage-backend`'s <backend_name> and to list valid options for
# that stage's category in the error message (mirrors pipeline_builder.py's
# stage-type-to-registry mapping -- VALID_STAGE_TYPES' three entries line up
# 1:1 with these three registries).
_STAGE_BACKEND_REGISTRY = {
    "connectivity": _CONNECTIVITY,
    "simulation": _SIMULATION,
    "synthesis": _SYNTHESIS,
}

# Same placeholder set format_tile_id() (veriflow/core/tile_id.py) accepts --
# kept in sync manually since id_format validation here is a pre-flight
# check (no tile context yet to compute real values against).
_ID_FORMAT_PLACEHOLDERS = frozenset({
    "prefix", "date", "tile_number", "version", "revision",
    "shuttle_name", "interface", "technology", "author_initials", "short_hash",
})


def _unknown_key_error(key: str, valid_keys: tuple[str, ...]) -> VeriFlowError:
    return VeriFlowError(
        f"Unsupported key: {key!r}. Valid keys: {', '.join(valid_keys)}",
        code="VF_SET_KEY_UNKNOWN",
        details={"key": key, "valid_keys": list(valid_keys)},
    )


def _validate_interface_value(value: str) -> str | None:
    """Returns the value to store (None clears the interface), or raises
    VeriFlowError(VF_SET_INTERFACE_INVALID)."""
    if value.strip().lower() in ("null", "none"):
        return None
    if has_interface_profile(value):
        return value
    if value.endswith(".v") and Path(value).is_file():
        return value
    raise VeriFlowError(
        f"Unknown interface profile or file: {value!r}. Must be a registered "
        "interface profile name, an existing .v file path, or 'null'/'none' to clear it.",
        code="VF_SET_INTERFACE_INVALID",
        details={"value": value},
    )


def _validate_technology_value(name: str) -> str:
    get_technology_profile(name)  # raises VF_TECHNOLOGY_UNKNOWN for an unregistered name
    return name


def _parse_bool_value(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in ("true", "1", "yes"):
        return True
    if normalized in ("false", "0", "no"):
        return False
    raise VeriFlowError(
        f"Invalid boolean value: {value!r}. Use 'true' or 'false'.",
        code="VF_SET_BOOL_INVALID",
        details={"value": value},
    )


def _parse_pipeline_value(value: str) -> list[dict]:
    types = [t.strip() for t in value.split(",") if t.strip()]
    if not types:
        raise VeriFlowError(
            "pipeline value must be a non-empty comma-separated list of stage types, "
            f"e.g. 'connectivity,synthesis'. Valid types: {', '.join(VALID_STAGE_TYPES)}",
            code="VF_PIPELINE_STAGE_UNKNOWN",
            details={"value": value, "valid_types": list(VALID_STAGE_TYPES)},
        )
    for stage_type in types:
        if stage_type not in VALID_STAGE_TYPES:
            raise VeriFlowError(
                f"Unknown pipeline stage type: {stage_type!r}. Valid types: {', '.join(VALID_STAGE_TYPES)}",
                code="VF_PIPELINE_STAGE_UNKNOWN",
                details={"type": stage_type, "valid_types": list(VALID_STAGE_TYPES)},
            )
    return [{"type": stage_type} for stage_type in types]


def _validate_stage_backend_value(value: str) -> tuple[str, str]:
    """Parses `stage-backend`'s "<stage_type>:<backend_name>" value.
    Returns (stage_type, backend_name). Raises VeriFlowError
    (VF_SET_STAGE_BACKEND_FORMAT_INVALID / VF_SET_STAGE_BACKEND_UNKNOWN)."""
    stage_type, sep, backend_name = value.partition(":")
    stage_type = stage_type.strip()
    backend_name = backend_name.strip()
    if not sep or stage_type not in VALID_STAGE_TYPES or not backend_name:
        raise VeriFlowError(
            f"Invalid stage-backend value: {value!r}. Expected format "
            "'<stage_type>:<backend_name>', e.g. 'simulation:xsim'. "
            f"Valid stage types: {', '.join(VALID_STAGE_TYPES)}",
            code="VF_SET_STAGE_BACKEND_FORMAT_INVALID",
            details={"value": value, "valid_types": list(VALID_STAGE_TYPES)},
        )
    registry = _STAGE_BACKEND_REGISTRY[stage_type]
    if backend_name not in registry:
        raise VeriFlowError(
            f"Unknown {stage_type} backend: {backend_name!r}. "
            f"Available {stage_type} backends: {', '.join(sorted(registry))}",
            code="VF_SET_STAGE_BACKEND_UNKNOWN",
            details={
                "stage_type": stage_type,
                "backend": backend_name,
                "valid_backends": sorted(registry),
            },
        )
    return stage_type, backend_name


def _stage_to_dict(stage) -> dict:
    d = {"type": stage.type}
    if stage.backend:
        d["backend"] = stage.backend
    return d


def _load_current_pipeline_stages(config_path: Path) -> list[dict]:
    """Current `pipeline.stages` as a list of {"type", ["backend"]} dicts,
    read directly from *config_path* (a plain, read-only yaml.safe_load --
    not the comment-preserving editor, which is write-only). Falls back to
    DEFAULT_PIPELINE (all three stage types, no backend override) when the
    file has no `pipeline:` section yet."""
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    pipeline_section = raw.get("pipeline")
    if isinstance(pipeline_section, dict) and pipeline_section.get("stages"):
        parsed = PipelineConfig.from_dict(pipeline_section)
    else:
        parsed = DEFAULT_PIPELINE
    return [_stage_to_dict(s) for s in parsed.stages]


def _apply_stage_backend(config_path: Path, value: str) -> None:
    """Implements the `stage-backend` key: update only the named stage's
    `backend` field in the current pipeline, leaving every other stage (and
    its own backend, if any) untouched. Raises VeriFlowError
    (VF_STAGE_NOT_IN_PIPELINE) if *stage_type* isn't part of the current
    pipeline -- add it first via the `pipeline` key."""
    stage_type, backend_name = _validate_stage_backend_value(value)
    stages = _load_current_pipeline_stages(config_path)
    for stage in stages:
        if stage["type"] == stage_type:
            stage["backend"] = backend_name
            break
    else:
        raise VeriFlowError(
            f"Stage {stage_type!r} is not in the current pipeline for {config_path}. "
            f"Add it first, e.g. `pipeline` = a comma-separated list including {stage_type!r}.",
            code="VF_STAGE_NOT_IN_PIPELINE",
            details={"stage_type": stage_type, "config": str(config_path)},
        )
    set_yaml_pipeline(config_path, stages)


def _validate_id_format_value(value: str) -> str:
    try:
        value.format(**{p: "" for p in _ID_FORMAT_PLACEHOLDERS})
    except (KeyError, IndexError, ValueError) as exc:
        raise VeriFlowError(
            f"Invalid id_format {value!r}: {exc}. "
            f"Available placeholders: {', '.join(sorted(_ID_FORMAT_PLACEHOLDERS))}",
            code="VF_ID_FORMAT_INVALID",
            details={"id_format": value},
        ) from exc
    return value


def _parse_source_list_value(value: str) -> list[str]:
    sources = [s.strip() for s in value.split(",") if s.strip()]
    if not sources:
        raise VeriFlowError(
            "value must be a non-empty comma-separated list of file paths, "
            "e.g. 'src/top.v,src/helper.v'",
            code="VF_SET_SOURCE_LIST_EMPTY",
            details={"value": value},
        )
    return sources


def _warn_missing_sources(config_path: Path, sources: list[str]) -> None:
    """Warn (don't error) for any entry that doesn't resolve to a real file
    relative to config_path's directory -- the user may be preparing the
    config before the RTL/TB files exist yet, e.g. scaffolding
    `rtl_sources`/`tb_sources` ahead of adding the actual sources."""
    root = config_path.parent
    for rel in sources:
        if not (root / rel).is_file():
            warnings.warn(
                f"Source file not found: {rel!r} (resolved relative to {root}). "
                "The value was set anyway -- add the file before running "
                "'veriflow project run'. [VF_SET_SOURCE_NOT_FOUND]",
                stacklevel=2,
            )


def _tile_number_str(tile: str | int) -> str:
    try:
        return f"{int(tile):04d}"
    except (TypeError, ValueError) as exc:
        raise VeriFlowError(
            f"Tile number must be numeric: {tile!r}",
            code="VF_TILE_NUMBER_INVALID",
            details={"tile": tile},
        ) from exc


# ── veriflow project set ────────────────────────────────────────────────────

def project_set_config(config_path: str | Path, key: str, value: str) -> dict:
    """Modify *config_path* (veriflow.yaml) for `key`/`value`. Returns
    {"key", "value", "config"}. Raises VeriFlowError for an unsupported key
    or an invalid value (unregistered interface/technology, bad pipeline
    stage type)."""
    config_path = Path(config_path)
    if not config_path.is_file():
        raise VeriFlowError(
            f"Project config not found: {config_path}",
            code="VF_PROJECT_CONFIG_NOT_FOUND",
            details={"path": str(config_path)},
        )

    if key == "interface":
        resolved = _validate_interface_value(value)
        if resolved is None:
            set_yaml_key(config_path, ("interface",), None)
        else:
            set_yaml_key(config_path, ("interface", "name"), resolved)
    elif key == "technology":
        _validate_technology_value(value)
        set_yaml_key(config_path, ("technology", "name"), value)
    elif key == "technology-strict":
        _validate_technology_value(value)
        set_yaml_nested_keys(config_path, "technology", {"name": value, "require_pdk": True})
    elif key == "require-pdk":
        set_yaml_key(config_path, ("technology", "require_pdk"), _parse_bool_value(value))
    elif key == "top-module":
        set_yaml_key(config_path, ("design", "top_module"), value)
    elif key == "pipeline":
        stages = _parse_pipeline_value(value)
        set_yaml_pipeline(config_path, stages)
    elif key == "stage-backend":
        _apply_stage_backend(config_path, value)
    elif key == "runs-dir":
        set_yaml_key(config_path, ("output", "runs_dir"), value)
    elif key == "rtl-sources":
        sources = _parse_source_list_value(value)
        _warn_missing_sources(config_path, sources)
        set_yaml_key(config_path, ("design", "rtl_sources"), sources)
    elif key == "tb-sources":
        sources = _parse_source_list_value(value)
        _warn_missing_sources(config_path, sources)
        set_yaml_key(config_path, ("design", "tb_sources"), sources)
    elif key == "tb-top":
        set_yaml_key(config_path, ("simulation", "tb_top"), value, quoted=True)
    elif key == "name":
        set_yaml_key(config_path, ("metadata", "name"), value, quoted=True)
    elif key == "author":
        set_yaml_key(config_path, ("metadata", "author"), value, quoted=True)
    elif key == "description":
        set_yaml_key(config_path, ("metadata", "description"), value, block_scalar=True)
    elif key == "version":
        set_yaml_key(config_path, ("metadata", "version"), value, quoted=True)
    else:
        raise _unknown_key_error(key, _PROJECT_SET_KEYS)

    return {"key": key, "value": value, "config": str(config_path)}


def cmd_project_set(args: argparse.Namespace) -> int:
    result = project_set_config(args.config, args.key, args.value)
    print_done(f"Set {result['key']} = {result['value']!r} in {result['config']}")
    return 0


# ── veriflow db set ──────────────────────────────────────────────────────────

def db_set_config(db_path: str | Path, key: str, value: str) -> dict:
    """Modify db_path/project_config.yaml for `key`/`value`. Returns
    {"key", "value", "config"}."""
    db = Path(db_path)
    config_path = db / "project_config.yaml"
    if not config_path.is_file():
        raise VeriFlowError(
            f"project_config.yaml not found in database: {db}",
            code="VF_DB_MISSING_REQUIRED_PATH",
            details={"path": str(config_path)},
        )

    if key == "interface":
        resolved = _validate_interface_value(value)
        set_yaml_key(config_path, ("interface_name",), resolved)
    elif key == "technology":
        _validate_technology_value(value)
        set_yaml_key(config_path, ("technology", "name"), value)
    elif key == "technology-strict":
        _validate_technology_value(value)
        set_yaml_nested_keys(config_path, "technology", {"name": value, "require_pdk": True})
    elif key == "require-pdk":
        set_yaml_key(config_path, ("technology", "require_pdk"), _parse_bool_value(value))
    elif key == "id-format":
        _validate_id_format_value(value)
        set_yaml_key(config_path, ("id_format",), value, quoted=True)
    elif key == "prefix":
        set_yaml_key(config_path, ("id_prefix",), value, quoted=True)
    elif key == "shuttle":
        set_yaml_key(config_path, ("shuttle_name",), value, quoted=True)
    elif key == "pipeline":
        stages = _parse_pipeline_value(value)
        set_yaml_pipeline(config_path, stages)
    elif key == "stage-backend":
        _apply_stage_backend(config_path, value)
    else:
        raise _unknown_key_error(key, _DB_SET_KEYS)

    return {"key": key, "value": value, "config": str(config_path)}


def cmd_db_set(args: argparse.Namespace) -> int:
    db = Path(args.db).resolve()
    result = db_set_config(db, args.key, args.value)
    print_done(f"Set {result['key']} = {result['value']!r} in {result['config']}")
    return 0


# ── veriflow db tile set ─────────────────────────────────────────────────────

def db_tile_set_config(db_path: str | Path, tile: str | int, key: str, value: str) -> dict:
    """Modify db_path/config/tile_<NNNN>/tile_config.yaml for `key`/`value`.
    Returns {"key", "value", "tile", "config"}."""
    db = Path(db_path)
    tile_number_str = _tile_number_str(tile)
    config_path = db / "config" / f"tile_{tile_number_str}" / "tile_config.yaml"
    if not config_path.is_file():
        raise VeriFlowError(
            f"tile_config.yaml not found for tile {tile_number_str}: {config_path}",
            code="VF_TILE_CONFIG_NOT_FOUND",
            details={"path": str(config_path), "tile": tile_number_str},
        )

    if key == "top-module":
        set_yaml_key(config_path, ("top_module",), value, quoted=True)
    elif key == "tb-top":
        set_yaml_key(config_path, ("tb_top_module",), value, quoted=True)
    elif key == "name":
        set_yaml_key(config_path, ("tile_name",), value, quoted=True)
    elif key == "author":
        set_yaml_key(config_path, ("tile_author",), value, quoted=True)
    elif key == "description":
        set_yaml_key(config_path, ("description",), value, block_scalar=True)
    elif key == "tags":
        set_yaml_key(config_path, ("tags",), value, quoted=True)
    elif key == "objective":
        set_yaml_key(config_path, ("objective",), value, quoted=True)
    elif key == "pipeline":
        stages = _parse_pipeline_value(value)
        set_yaml_pipeline(config_path, stages)
    elif key == "stage-backend":
        _apply_stage_backend(config_path, value)
    elif key == "require-pdk":
        set_yaml_key(config_path, ("technology", "require_pdk"), _parse_bool_value(value))
    else:
        raise _unknown_key_error(key, _DB_TILE_SET_KEYS)

    return {"key": key, "value": value, "tile": tile_number_str, "config": str(config_path)}


def cmd_db_tile_set(args: argparse.Namespace) -> int:
    db = Path(args.db).resolve()
    result = db_tile_set_config(db, args.tile, args.key, args.value)
    print_done(
        f"Set {result['key']} = {result['value']!r} for tile {result['tile']} in {result['config']}"
    )
    return 0
