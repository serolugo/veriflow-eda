from dataclasses import dataclass
from pathlib import Path


@dataclass
class RunContext:
    tile_id: str
    run_id: str
    tile_dir: Path
    run_dir: Path
    semicolab: bool
    skip_connectivity: bool
    skip_sim: bool
    skip_synth: bool
    db_path: Path | None = None

    def log_rel(self, path: Path) -> str:
        """Return path relative to db/tiles when db_path is set, else as_posix()."""
        if self.db_path is None:
            return path.as_posix()
        try:
            return "tiles/" + path.relative_to(self.db_path / "tiles").as_posix()
        except ValueError:
            return path.as_posix()

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
