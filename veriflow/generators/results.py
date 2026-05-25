import json
from pathlib import Path


def generate_results_json(data: dict, output_path: Path) -> None:
    output_path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
