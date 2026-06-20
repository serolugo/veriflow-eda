import shutil
from datetime import date
from pathlib import Path

from veriflow.core import VeriFlowError
from veriflow.core.csv_store import get_tile_row, update_tile_index
from veriflow.core.tile_id import generate_tile_id, parse_tile_id
from veriflow.core.validator import validate_database


def cmd_bump_version(db: Path, tile_number: str) -> None:
    """
    Increment id_version. Revision stays the same.
    Old tile dir is preserved. New tile dir starts clean (no runs),
    works/ is copied from the old tile.
    """
    validate_database(db)
    try:
        tile_number_str = f"{int(tile_number):04d}"
    except ValueError:
        raise VeriFlowError(
            f"Tile number must be numeric: {tile_number!r}",
            code="VF_TILE_NUMBER_INVALID",
            details={"tile_number": tile_number},
        )
    tile_index_path = db / "tile_index.csv"

    # 1. Read current tile_id
    tile_row = get_tile_row(tile_index_path, tile_number_str)
    old_tile_id = tile_row["tile_id"]
    print(f"[bump-version] Current tile_id : {old_tile_id}")

    # 2. Parse and increment id_version — revision stays the same
    parsed = parse_tile_id(old_tile_id)
    new_version = parsed["id_version"] + 1
    new_revision = parsed["id_revision"]  # unchanged

    # 3. Generate new tile_id with today's date
    new_tile_id = generate_tile_id(
        parsed["id_prefix"],
        parsed["tile_number"],
        new_version,
        new_revision,
        today=date.today(),
    )
    print(f"[bump-version] New tile_id     : {new_tile_id}")

    # 4. Create new tile dir (old dir is preserved)
    old_dir = db / "tiles" / old_tile_id
    new_dir = db / "tiles" / new_tile_id
    if not old_dir.exists():
        raise VeriFlowError(f"Tile directory not found: {old_dir}")
    if new_dir.exists():
        raise VeriFlowError(f"New tile directory already exists: {new_dir}")

    new_dir.mkdir(parents=True)
    print(f"[bump-version] Created tiles/{new_tile_id}/")

    # 5. Copy works/ from old tile
    old_works = old_dir / "works"
    new_works = new_dir / "works"
    if old_works.exists():
        shutil.copytree(old_works, new_works)
        print(f"[bump-version] Copied works/ from {old_tile_id}")
    else:
        for sub in ("works/rtl", "works/tb"):
            d = new_dir / sub
            d.mkdir(parents=True, exist_ok=True)
            (d / ".gitkeep").touch()

    # 6. Copy README.md from old tile
    old_readme = old_dir / "README.md"
    if old_readme.exists():
        shutil.copy2(old_readme, new_dir / "README.md")

    # 7. Create clean runs/
    runs_dir = new_dir / "runs"
    runs_dir.mkdir()
    (runs_dir / ".gitkeep").touch()
    print(f"[bump-version] Created clean runs/")

    # 8. Update tile_index.csv
    updated_row = {
        "tile_number": tile_number_str,
        "tile_id": new_tile_id,
        "tile_name": tile_row["tile_name"],
        "tile_author": tile_row["tile_author"],
        "interface_name": tile_row.get("interface_name", ""),
        "version": f"{new_version:02d}",
        "revision": f"{new_revision:02d}",
    }
    update_tile_index(tile_index_path, tile_number_str, updated_row)
    print(f"[bump-version] Updated tile_index.csv")

    print()
    print("✓ Version bumped successfully.")
    print(f"  Old tile_id : {old_tile_id}  (preserved)")
    print(f"  New tile_id : {new_tile_id}")
    print(f"  Version     : {parsed['id_version']:02d} → {new_version:02d}")
    print(f"  Revision    : {new_revision:02d} (unchanged)")
