from __future__ import annotations

from dataclasses import dataclass


@dataclass
class StageResult:
    name: str
    status: str
    tool: str | None = None
    log_paths: list[str] | None = None
    artifacts: dict | None = None
    metrics: dict | None = None
    error: dict | None = None
    warnings: list[str] | None = None
    technology: str | None = None            # synthesis only: technology name actually used for PDK-mapped synthesis
    technology_version: str | None = None     # synthesis only: installed PDK version/commit hash, for traceability

    def to_dict(self) -> dict:
        d: dict = {}
        if self.tool is not None:
            d["tool"] = self.tool
        d["status"] = self.status
        if self.log_paths:
            d["logs"] = self.log_paths
        if self.artifacts:
            d["artifacts"] = self.artifacts
        if self.metrics:
            d["metrics"] = self.metrics
        if self.error is not None:
            d["error"] = self.error
        if self.warnings:
            d["warnings"] = self.warnings
        if self.technology is not None:
            d["technology"] = self.technology
        if self.technology_version is not None:
            d["technology_version"] = self.technology_version
        return d
