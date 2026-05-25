from dataclasses import dataclass
from pathlib import Path


@dataclass
class RunContext:
    db_path: Path
    tile_id: str
    run_id: str
    tile_dir: Path
    run_dir: Path
    tile_config_path: Path
    project_config_path: Path
    semicolab: bool
    skip_connectivity: bool
    skip_sim: bool
    skip_synth: bool

    @property
    def src_dir(self) -> Path:
        return self.run_dir / "src"

    @property
    def out_dir(self) -> Path:
        return self.run_dir / "out"

    @property
    def sim_dir(self) -> Path:
        return self.out_dir / "sim"

    @property
    def synth_dir(self) -> Path:
        return self.out_dir / "synth"

    @property
    def impl_dir(self) -> Path:
        return self.out_dir / "connectivity"

    @property
    def manifest_path(self) -> Path:
        return self.run_dir / "manifest.yaml"

    @property
    def summary_path(self) -> Path:
        return self.run_dir / "summary.md"

    @property
    def notes_path(self) -> Path:
        return self.run_dir / "notes.md"

    @property
    def results_path(self) -> Path:
        return self.run_dir / "results.json"
