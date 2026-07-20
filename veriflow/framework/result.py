from __future__ import annotations

from dataclasses import dataclass

from veriflow.framework.status import derive_run_status
from veriflow.models.stage_result import StageResult


def _derive_status(stages: dict[str, StageResult]) -> str:
    return derive_run_status(sr.status for sr in stages.values())


@dataclass
class RunResult:
    status: str
    stages: dict[str, StageResult]

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "stages": {name: sr.to_dict() for name, sr in self.stages.items()},
        }

    @classmethod
    def from_stages(cls, stages: dict[str, StageResult]) -> "RunResult":
        return cls(status=_derive_status(stages), stages=stages)


__all__ = ["RunResult"]
