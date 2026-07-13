from pathlib import Path

from veriflow.core import VeriFlowError


_PROJECT_CONFIG_TEMPLATE = """\
id_prefix: ""
project_name: ""
repo: ""
interface_name: null  # set to a registered profile name (e.g. "semicolab") to enable connectivity checking
description: |

# shuttle_name: ""    # optional -- used by the {shuttle_name} id_format placeholder

# id_format: "{prefix}-{date}{tile_number}{version}{revision}"  # optional -- default shown; customize the tile_id layout
#   Available placeholders:
#     {prefix}          -- id_prefix (above)
#     {date}            -- create-tile date, YYMMDD
#     {tile_number}     -- tile number, zero-padded to 4 digits
#     {version}         -- id_version, zero-padded to 2 digits
#     {revision}        -- id_revision, zero-padded to 2 digits
#     {shuttle_name}    -- shuttle_name (above)
#     {interface}       -- interface_name (above)
#     {technology}      -- technology.name below, or "generic" if unset
#     {author_initials} -- initials of tile_author (--tile-author or tile_config.yaml)
#     {short_hash}      -- not yet available; resolves to "000000" with a warning

# technology:
#   name: generic       # optional -- used by the {technology} id_format placeholder
"""


def cmd_init(db: Path, force: bool = False) -> None:
    """Initialize a new VeriFlow database at the given path."""

    if db.exists() and not force:
        raise VeriFlowError(
            f"Database directory already exists: {db}\n"
            f"  Use --force to overwrite."
        )

    print(f"[init] Creating database at {db}")

    # 1. Create root
    db.mkdir(parents=True, exist_ok=True)

    # 2. Create tiles/
    tiles_dir = db / "tiles"
    tiles_dir.mkdir(exist_ok=True)
    (tiles_dir / ".gitkeep").touch()
    print(f"[init] Created tiles/")

    # 3. Create config/
    config_dir = db / "config"
    config_dir.mkdir(exist_ok=True)
    print(f"[init] Created config/")

    # 4. Write project_config.yaml template
    project_cfg = db / "project_config.yaml"
    project_cfg.write_text(_PROJECT_CONFIG_TEMPLATE, encoding="utf-8")
    print(f"[init] Written project_config.yaml")

    # 5. Create tile_index.csv (empty)
    tile_index = db / "tile_index.csv"
    tile_index.write_text("", encoding="utf-8")
    print(f"[init] Created tile_index.csv")

    # 6. Create records.csv (empty)
    records = db / "records.csv"
    records.write_text("", encoding="utf-8")
    print(f"[init] Created records.csv")

    print()
    print("✓ Database initialized successfully.")
    print(f"  Path : {db.resolve()}")
    print(f"  Next : Fill in {db / 'project_config.yaml'}")
