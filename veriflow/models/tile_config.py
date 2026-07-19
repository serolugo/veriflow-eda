from dataclasses import dataclass, field

from veriflow.core import VeriFlowError
from veriflow.models.pipeline_config import PipelineConfig, parse_optional_pipeline_section

DEFAULT_TB_TOP_MODULE = "tb"

# Every top-level key tile_config.yaml's parser actually reads. Same
# silent-unknown-key risk as project_config.yaml (models/project_config.py)
# -- a tile_config.yaml with e.g. a stray `execution:` section would
# otherwise be dropped with no error and no indication why it had no effect.
_KNOWN_TOP_LEVEL_KEYS = frozenset({
    "tile_name", "tile_author", "top_module", "tb_top_module",
    "description", "ports", "usage_guide", "tb_description",
    "run_author", "objective", "tags", "main_change", "notes",
    "pipeline", "technology",
})

_EXECUTION_KEY_HINT = (
    "Database Mode specifies simulation backend per-stage via "
    "pipeline.stages[].backend (this tile's own pipeline: section may "
    "override it), not a top-level execution: section. "
    "See docs/PROJECT_CONFIG.md."
)


def _parse_tile_technology_section(data: dict) -> bool | None:
    """Parse tile_config.yaml's optional `technology:` section -- only
    `require_pdk` is supported here (unlike Project Mode/database-level
    `technology:`, a tile has no `name`/`definition` override of its own;
    technology *name* stays database-wide, set only in project_config.yaml).

    Returns None ("not set here" -- inherit project_config.yaml's
    require_pdk) when the section is absent or present but empty/
    `require_pdk` omitted.
    """
    section = data.get("technology")
    if section is None:
        return None
    if not isinstance(section, dict):
        raise VeriFlowError(
            "tile technology section must be a mapping, e.g.:\n"
            "    technology:\n"
            "      require_pdk: true",
            code="VF_TILE_TECHNOLOGY_CONFIG_INVALID",
            details={"technology": section},
        )
    unknown_keys = sorted(set(section) - {"require_pdk"})
    if unknown_keys:
        raise VeriFlowError(
            f"Unsupported keys in tile technology section: {', '.join(unknown_keys)}.\n"
            "  Supported keys: 'require_pdk' (technology name is database-wide, "
            "set in project_config.yaml, not per-tile).",
            code="VF_TILE_TECHNOLOGY_CONFIG_INVALID",
            details={"unknown_keys": unknown_keys},
        )
    raw_require_pdk = section.get("require_pdk")
    if raw_require_pdk is None:
        return None
    if not isinstance(raw_require_pdk, bool):
        raise VeriFlowError(
            "technology.require_pdk must be a boolean (true/false)",
            code="VF_TILE_TECHNOLOGY_CONFIG_INVALID",
            details={"require_pdk": raw_require_pdk},
        )
    return raw_require_pdk


@dataclass
class TileConfig:
    # ── Tile (permanent) ──────────────────────────────────────────────────────
    tile_name: str
    tile_author: str
    top_module: str
    tb_top_module: str
    description: str
    ports: str
    usage_guide: str
    tb_description: str
    # ── Run (updated each run) ────────────────────────────────────────────────
    run_author: str
    objective: str
    tags: str
    main_change: str
    notes: str
    # ── Pipeline override (optional; None = inherit from project_config.yaml) ─
    pipeline: PipelineConfig | None = None
    # ── Technology require_pdk override (optional; None = inherit) ───────────
    require_pdk: bool | None = None
    # Config-parse-time warnings (currently: unknown top-level keys) --
    # surfaced in the run's own results data and via print_warn(), not
    # raised as Python UserWarning. Same mechanism as ProjectConfig's.
    config_warnings: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict) -> "TileConfig":
        config_warnings: list[str] = []
        unknown_keys = sorted(set(data) - _KNOWN_TOP_LEVEL_KEYS)
        for key in unknown_keys:
            if key == "execution":
                config_warnings.append(f"Unknown key {key!r} in tile_config.yaml -- {_EXECUTION_KEY_HINT}")
            else:
                config_warnings.append(
                    f"Unknown key {key!r} in tile_config.yaml -- ignored. "
                    "See docs/PROJECT_CONFIG.md for the recognized tile_config.yaml schema."
                )

        raw_tb_top = data.get("tb_top_module")
        tb_top_module = raw_tb_top if raw_tb_top is not None else DEFAULT_TB_TOP_MODULE
        # Raises VF_PIPELINE_CONFIG_INVALID / VF_PIPELINE_STAGE_UNKNOWN for a malformed
        # section. None means "not set here" -- inherit project_config.yaml's pipeline.
        pipeline = parse_optional_pipeline_section(data)
        # Raises VF_TILE_TECHNOLOGY_CONFIG_INVALID for a malformed section.
        # None means "not set here" -- inherit project_config.yaml's require_pdk.
        require_pdk = _parse_tile_technology_section(data)
        return cls(
            tile_name=data.get("tile_name", "") or "",
            tile_author=data.get("tile_author", "") or "",
            top_module=data.get("top_module", "") or "",
            tb_top_module=tb_top_module,
            description=data.get("description", "") or "",
            ports=data.get("ports", "") or "",
            usage_guide=data.get("usage_guide", "") or "",
            tb_description=data.get("tb_description", "") or "",
            run_author=data.get("run_author", "") or "",
            objective=data.get("objective", "") or "",
            tags=data.get("tags", "") or "",
            main_change=data.get("main_change", "") or "",
            notes=data.get("notes", "") or "",
            pipeline=pipeline,
            require_pdk=require_pdk,
            config_warnings=config_warnings,
        )
