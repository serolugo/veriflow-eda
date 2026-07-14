"""Configurable pipeline: which stages run, in what order, on what backend.

Used by all three config layers:
  - veriflow.yaml (Project Mode, ``ProjectWorkflowConfig.pipeline``)
  - project_config.yaml (Database Mode, ``ProjectConfig.pipeline`` -- default for all tiles)
  - tile_config.yaml (Database Mode, ``TileConfig.pipeline`` -- per-tile override)

A ``pipeline:`` section absent from a config means "use the current default
behavior" (all three stages, in order, default backend) -- see
``DEFAULT_PIPELINE``. Database Mode resolves the *effective* pipeline as
tile_config.pipeline, else project_config.pipeline, else DEFAULT_PIPELINE.
"""

from __future__ import annotations

from dataclasses import dataclass

from veriflow.core import VeriFlowError

VALID_STAGE_TYPES = ("connectivity", "simulation", "synthesis")


@dataclass(frozen=True)
class PipelineStageConfig:
    type: str
    backend: str | None = None


@dataclass(frozen=True)
class PipelineConfig:
    stages: tuple[PipelineStageConfig, ...]

    @classmethod
    def from_dict(cls, data: dict) -> "PipelineConfig":
        """Parse a ``pipeline:`` section (the mapping under the ``pipeline``
        key itself, e.g. ``{"stages": [...]}``).

        Raises VeriFlowError(VF_PIPELINE_STAGE_UNKNOWN) if any stage entry's
        `type` is missing or not a registered stage type. Extra keys on a
        stage entry (e.g. a future `timeout:`) are ignored silently, for
        forward compatibility with fields not implemented yet.
        """
        raw_stages = data.get("stages") or []
        stages = []
        for raw_stage in raw_stages:
            stage_type = raw_stage.get("type") if isinstance(raw_stage, dict) else None
            if stage_type not in VALID_STAGE_TYPES:
                raise VeriFlowError(
                    f"Unknown pipeline stage type: {stage_type!r}. "
                    f"Valid types: {', '.join(VALID_STAGE_TYPES)}",
                    code="VF_PIPELINE_STAGE_UNKNOWN",
                    details={"type": stage_type, "valid_types": list(VALID_STAGE_TYPES)},
                )
            raw_backend = raw_stage.get("backend")
            backend = raw_backend.strip() if isinstance(raw_backend, str) and raw_backend.strip() else None
            stages.append(PipelineStageConfig(type=stage_type, backend=backend))
        return cls(stages=tuple(stages))

    def has_stage(self, stage_type: str) -> bool:
        return any(s.type == stage_type for s in self.stages)

    def backend_for(self, stage_type: str) -> str | None:
        """Return the configured backend override for stage_type, or None if
        the stage isn't in the pipeline or doesn't specify one."""
        for s in self.stages:
            if s.type == stage_type:
                return s.backend
        return None


DEFAULT_PIPELINE = PipelineConfig.from_dict({
    "stages": [
        {"type": "connectivity"},
        {"type": "simulation"},
        {"type": "synthesis"},
    ],
})


def parse_optional_pipeline_section(data: dict) -> "PipelineConfig | None":
    """Parse an optional top-level ``pipeline:`` section shared by
    veriflow.yaml, project_config.yaml, and tile_config.yaml.

    Returns None if the section is absent (or `pipeline: null`) -- the
    caller decides the fallback: DEFAULT_PIPELINE for Project Mode (no
    inheritance chain), or None to signal "inherit from a parent config"
    for Database Mode's project_config.yaml/tile_config.yaml pair.
    """
    section = data.get("pipeline")
    if section is None:
        return None
    if not isinstance(section, dict):
        raise VeriFlowError(
            "pipeline section must be a mapping with a 'stages' key, e.g.:\n"
            "    pipeline:\n"
            "      stages:\n"
            "        - type: connectivity",
            code="VF_PIPELINE_CONFIG_INVALID",
            details={"pipeline": section},
        )
    return PipelineConfig.from_dict(section)
