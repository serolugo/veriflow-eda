from pathlib import Path

from veriflow.models.tile_config import TileConfig


def generate_notes(
    tile_id: str,
    tile_config: TileConfig,
    output_path: Path,
) -> None:
    content = f"""# Tile ID : "{tile_id}"

## Title: "{tile_config.tile_name}"

## Notes:
"{tile_config.notes}"
"""
    output_path.write_text(content, encoding="utf-8")
