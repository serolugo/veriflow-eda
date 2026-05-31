from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class RunRequest:
    work_dir: Path
    semicolab: bool = False
    skip_connectivity: bool = False
    skip_sim: bool = False
    skip_synth: bool = False

    def __post_init__(self) -> None:
        self.work_dir = Path(self.work_dir)


__all__ = ["RunRequest"]
