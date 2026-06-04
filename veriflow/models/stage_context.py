from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


class StageContext(Protocol):
    """Minimum contract consumed by built-in stages."""

    run_dir: Path
    skip_connectivity: bool
    skip_sim: bool
    skip_synth: bool

    @property
    def out_dir(self) -> Path: ...

    @property
    def impl_dir(self) -> Path: ...

    @property
    def sim_dir(self) -> Path: ...

    @property
    def synth_dir(self) -> Path: ...

    def log_rel(self, path: Path) -> str: ...


@dataclass
class ExecutionContext:
    """Database-independent execution context for framework/API flows."""

    run_dir: Path
    skip_connectivity: bool = False
    skip_sim: bool = False
    skip_synth: bool = False

    def __post_init__(self) -> None:
        self.run_dir = Path(self.run_dir)

    @property
    def out_dir(self) -> Path:
        return self.run_dir / "out"

    @property
    def impl_dir(self) -> Path:
        return self.out_dir / "connectivity"

    @property
    def sim_dir(self) -> Path:
        return self.out_dir / "sim"

    @property
    def synth_dir(self) -> Path:
        return self.out_dir / "synth"

    def log_rel(self, path: Path) -> str:
        try:
            return path.relative_to(self.run_dir).as_posix()
        except ValueError:
            return path.as_posix()


__all__ = ["StageContext", "ExecutionContext"]
