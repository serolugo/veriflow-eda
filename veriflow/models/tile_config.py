from dataclasses import dataclass

from veriflow.models.pipeline_config import PipelineConfig, parse_optional_pipeline_section

DEFAULT_TB_TOP_MODULE = "tb"


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

    @classmethod
    def from_dict(cls, data: dict) -> "TileConfig":
        raw_tb_top = data.get("tb_top_module")
        tb_top_module = raw_tb_top if raw_tb_top is not None else DEFAULT_TB_TOP_MODULE
        # Raises VF_PIPELINE_CONFIG_INVALID / VF_PIPELINE_STAGE_UNKNOWN for a malformed
        # section. None means "not set here" -- inherit project_config.yaml's pipeline.
        pipeline = parse_optional_pipeline_section(data)
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
        )
