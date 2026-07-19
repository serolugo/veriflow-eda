from dataclasses import dataclass

from veriflow.core import VeriFlowError
from veriflow.models.pipeline_config import PipelineConfig, parse_optional_pipeline_section

DEFAULT_TB_TOP_MODULE = "tb"


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

    @classmethod
    def from_dict(cls, data: dict) -> "TileConfig":
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
        )
