import csv
from pathlib import Path
from typing import Optional

from veriflow.core import VeriFlowError

TILE_INDEX_HEADER = ["tile_number", "tile_id", "tile_name", "tile_author", "version", "revision", "interface_name"]
RECORDS_HEADER = [
    "Tile_ID", "Run_ID", "Date", "Author", "Objective", "Status",
    "Version", "Revision", "Connectivity", "Simulation", "Synthesis",
    "Tool_Version", "Main_Change", "Run_Path", "Tags", "Interface",
]


def _read_csv(path: Path, expected_header: list[str]) -> list[dict]:
    """Read a CSV file and return list of row dicts. Validates header if file is non-empty."""
    content = path.read_text(encoding="utf-8").strip()
    if not content:
        return []
    reader = csv.DictReader(content.splitlines())
    if reader.fieldnames != expected_header:
        raise VeriFlowError(
            f"CSV header mismatch in {path}.\n"
            f"  Expected : {expected_header}\n"
            f"  Got      : {list(reader.fieldnames or [])}"
        )
    return list(reader)


def _write_csv(path: Path, header: list[str], rows: list[dict]) -> None:
    """Write rows to CSV, always writing header first."""
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=header)
        writer.writeheader()
        writer.writerows(rows)


def _ensure_header(path: Path, header: list[str]) -> None:
    """If the file is empty, write the header row."""
    if not path.stat().st_size:
        with path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=header)
            writer.writeheader()


# ---------- tile_index.csv ----------

def read_tile_index(path: Path) -> list[dict]:
    return _read_csv(path, TILE_INDEX_HEADER)


def append_tile_index(path: Path, row: dict) -> None:
    _ensure_header(path, TILE_INDEX_HEADER)
    with path.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=TILE_INDEX_HEADER)
        writer.writerow(row)


def update_tile_index(path: Path, tile_number: str, updated_row: dict) -> None:
    """Replace the row matching tile_number with updated_row."""
    rows = read_tile_index(path)
    new_rows = []
    found = False
    for row in rows:
        if row["tile_number"] == tile_number:
            new_rows.append(updated_row)
            found = True
        else:
            new_rows.append(row)
    if not found:
        raise VeriFlowError(f"Tile number {tile_number!r} not found in tile_index.csv")
    _write_csv(path, TILE_INDEX_HEADER, new_rows)


def get_tile_row(path: Path, tile_number: str) -> dict:
    """Return the row for a given tile_number, or raise VeriFlowError."""
    rows = read_tile_index(path)
    for row in rows:
        if row["tile_number"] == tile_number:
            return row
    raise VeriFlowError(f"Tile number {tile_number!r} not found in tile_index.csv")


def get_next_tile_number(path: Path) -> int:
    """Return the next available tile number (1-based)."""
    rows = read_tile_index(path)
    if not rows:
        return 1
    return max(int(r["tile_number"]) for r in rows) + 1


# ---------- records.csv ----------

def append_record(path: Path, row: dict) -> None:
    _ensure_header(path, RECORDS_HEADER)
    with path.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=RECORDS_HEADER)
        writer.writerow(row)
