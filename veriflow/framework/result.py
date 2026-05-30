from __future__ import annotations

from dataclasses import dataclass

from veriflow.models.stage_result import StageResult

_PASS_STATUSES = {"PASS", "COMPLETED", "SKIPPED"}


def _derive_status(stages: dict[str, StageResult]) -> str:
    for sr in stages.values():
        if sr.status not in _PASS_STATUSES:
            return "FAIL"
    return "PASS"


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
