from datetime import date

from veriflow.core import VeriFlowError

# Placeholders always available when formatting a tile_id (see format_tile_id).
_KNOWN_PLACEHOLDERS = (
    "prefix", "date", "tile_number", "version", "revision",
    "shuttle_name", "interface", "technology", "author_initials", "short_hash",
)


def compute_initials(full_name: str) -> str:
    """Return the uppercase initials of a person's name, e.g. "Roman Lugo" -> "RL".

    Empty or whitespace-only input returns "".
    """
    parts = [p for p in full_name.strip().split() if p]
    return "".join(p[0].upper() for p in parts)


def format_tile_id(id_format: str, placeholders: dict[str, str]) -> str:
    """Render id_format with the given placeholder values.

    Raises VeriFlowError(code="VF_ID_FORMAT_INVALID") if id_format references
    a placeholder name that isn't in `placeholders` (typically a user typo),
    or if the format string is otherwise malformed.
    """
    try:
        return id_format.format(**placeholders)
    except KeyError as exc:
        unknown = exc.args[0]
        raise VeriFlowError(
            f"Unknown placeholder '{{{unknown}}}' in id_format: {id_format!r}. "
            f"Available placeholders: {', '.join(sorted(placeholders))}",
            code="VF_ID_FORMAT_INVALID",
            details={"id_format": id_format, "unknown_placeholder": str(unknown)},
        ) from exc
    except (IndexError, ValueError) as exc:
        raise VeriFlowError(
            f"Invalid id_format {id_format!r}: {exc}",
            code="VF_ID_FORMAT_INVALID",
            details={"id_format": id_format},
        ) from exc


def generate_tile_id(
    id_prefix: str,
    tile_number: int,
    id_version: int = 1,
    id_revision: int = 1,
    today: date | None = None,
) -> str:
    """
    Format: <id_prefix>-<YYMMDD><tile_number:04d><id_version:02d><id_revision:02d>
    Example: MST130-01-26031500010101
    """
    if today is None:
        today = date.today()
    yymmdd = today.strftime("%y%m%d")
    tile_num_str = f"{tile_number:04d}"
    version_str = f"{id_version:02d}"
    revision_str = f"{id_revision:02d}"
    return f"{id_prefix}-{yymmdd}{tile_num_str}{version_str}{revision_str}"


def parse_tile_id(tile_id: str) -> dict:
    """
    Parse a tile_id into its components.
    Returns dict with keys: id_prefix, yymmdd, tile_number, id_version, id_revision
    The suffix after the last '-' is: YYMMDD(6) + tile_number(4) + version(2) + revision(2) = 14 chars
    """
    # Split on '-' but id_prefix may itself contain '-'
    # The numeric suffix is always the last 14 chars of the last segment
    # We find the last '-' that separates the numeric block
    parts = tile_id.rsplit("-", 1)
    if len(parts) != 2 or len(parts[1]) != 14:
        raise ValueError(f"Cannot parse tile_id: {tile_id!r}")
    id_prefix = parts[0]
    numeric = parts[1]
    yymmdd = numeric[0:6]
    tile_number = int(numeric[6:10])
    id_version = int(numeric[10:12])
    id_revision = int(numeric[12:14])
    return {
        "id_prefix": id_prefix,
        "yymmdd": yymmdd,
        "tile_number": tile_number,
        "id_version": id_version,
        "id_revision": id_revision,
    }
