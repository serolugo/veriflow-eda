from __future__ import annotations

from typing import Protocol

from veriflow.framework.stage_input import StageInput
from veriflow.models.stage_result import StageResult


class Stage(Protocol):
    name: str

    def run(self, input: StageInput) -> StageResult: ...


__all__ = ["Stage"]
