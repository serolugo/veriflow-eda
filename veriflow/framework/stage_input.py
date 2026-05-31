from __future__ import annotations

from dataclasses import dataclass, field

from veriflow.framework.design import Design
from veriflow.models.stage_context import StageContext
from veriflow.models.stage_result import StageResult


@dataclass
class StageInput:
    design: Design
    context: StageContext
    prior_results: dict[str, StageResult] = field(default_factory=dict)


__all__ = ["StageInput"]
