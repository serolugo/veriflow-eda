import re
from datetime import date
from pathlib import Path

import yaml

from veriflow.core import VeriFlowError
from veriflow.core.csv_store import append_tile_index, get_next_tile_number
from veriflow.core.tile_id import generate_tile_id
from veriflow.core.validator import validate_database, validate_project_config
from veriflow.generators.readme import generate_readme
from veriflow.models.project_config import ProjectConfig
from veriflow.models.tile_config import TileConfig

_VERILOG_ID_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_$]*$")


_TILE_CONFIG_TEMPLATE = """\
# =============================================================================
# TILE INFORMATION  (permanent -- fill once)
# =============================================================================

tile_name: ""       # Display name for this tile
tile_author: ""     # Your full name
top_module: ""      # Must match the RTL filename exactly (e.g. adder_tile)
tb_top_module: "tb" # Testbench top module name (module declared in tb_tile.v)

description: |
  # What does this tile do?

ports: |
  # Describe how your tile uses the SemiCoLab port convention:
  #   clk / arst_n     - clock and reset
  #   csr_in[15:0]     - control inputs
  #   data_reg_a / b   - input data (32-bit)
  #   data_reg_c       - output data (32-bit)
  #   csr_out[15:0]    - status outputs

usage_guide: |
  # How should this tile be used?

tb_description: |
  # Briefly describe your testbench approach

# =============================================================================
# RUN INFORMATION  (update before each run)
# =============================================================================

run_author: ""      # Who is running this verification
objective: ""       # What are you trying to verify in this run
tags: ""            # Comma-separated tags (e.g. initial, fix, refactor)

main_change: |
  # What changed since the last run?

notes: |
  # Any additional notes for this run
"""


def cmd_create_tile(db: Path, *, top_module: str = "") -> None:
    """Create a new tile entry in the database.

    top_module: RTL top module name.  Required for Semicolab projects (raises
    VF_TILE_TOP_MODULE_REQUIRED when missing).  When provided, it is written
    into tile_config.yaml AND substituted into src/tb/tb_tile.v so that both
    artifacts share the same declared DUT name as a single source of truth.
    """

    validate_database(db)

    # 1. Read project config
    project_cfg_path = db / "project_config.yaml"
    raw = yaml.safe_load(project_cfg_path.read_text(encoding="utf-8")) or {}
    project_config = ProjectConfig.from_dict(raw)
    validate_project_config(project_config)

    # 2. Validate top_module early — before any filesystem writes
    if project_config.semicolab:
        if not top_module or not top_module.strip():
            raise VeriFlowError(
                "top_module is required when creating a Semicolab tile. "
                "Pass the RTL top module name so the testbench can be generated correctly.",
                code="VF_TILE_TOP_MODULE_REQUIRED",
            )
        if not _VERILOG_ID_RE.match(top_module):
            raise VeriFlowError(
                f"top_module {top_module!r} is not a valid Verilog identifier. "
                "Must start with a letter or underscore and contain only "
                "letters, digits, underscores, or dollar signs.",
                code="VF_TILE_TOP_MODULE_INVALID",
                details={"top_module": top_module},
            )

    # 3. Get next tile_number
    tile_index_path = db / "tile_index.csv"
    tile_number = get_next_tile_number(tile_index_path)
    tile_number_str = f"{tile_number:04d}"

    # 4. Set version/revision
    id_version = 1
    id_revision = 1

    # 5. Generate tile_id
    tile_id = generate_tile_id(
        project_config.id_prefix,
        tile_number,
        id_version,
        id_revision,
        today=date.today(),
    )

    print(f"[create-tile] Generating tile {tile_number_str} -> {tile_id}")

    # 6. Create config/tile_XXXX/
    config_tile_dir = db / "config" / f"tile_{tile_number_str}"
    config_tile_dir.mkdir(parents=True, exist_ok=True)
    print(f"[create-tile] Created {config_tile_dir.relative_to(db)}")

    # 7. Write single tile_config.yaml (tile + run fields merged)
    config_text = _TILE_CONFIG_TEMPLATE
    if top_module:
        config_text = config_text.replace('top_module: ""', f'top_module: "{top_module}"')
    (config_tile_dir / "tile_config.yaml").write_text(config_text, encoding="utf-8")
    print(f"[create-tile] Written tile_config.yaml")

    # 8. Create src/rtl/ and src/tb/ with templates
    import shutil
    template_dir = Path(__file__).parent.parent / "template"
    for sub in ("src/rtl", "src/tb"):
        d = config_tile_dir / sub
        d.mkdir(parents=True, exist_ok=True)
        (d / ".gitkeep").touch()

    tb_dir = config_tile_dir / "src" / "tb"
    if project_config.semicolab:
        tb_semicolab = template_dir / "tb_semicolab_template.v"
        if tb_semicolab.exists():
            content = tb_semicolab.read_text(encoding="utf-8")
            content = content.replace("/* DUT_MODULE */", top_module)
            (tb_dir / "tb_tile.v").write_text(content, encoding="utf-8")
        print(f"[create-tile] Created src/rtl/ and src/tb/ (semicolab: tb_tile.v)")
    else:
        tb_universal = template_dir / "tb_universal_template.v"
        if tb_universal.exists():
            shutil.copy2(tb_universal, tb_dir / "tb_tile.v")
        print(f"[create-tile] Created src/rtl/ and src/tb/ (universal: empty tb_tile.v)")

    # 9. Create tiles/<tile_id>/
    tile_dir = db / "tiles" / tile_id
    tile_dir.mkdir(parents=True, exist_ok=True)
    print(f"[create-tile] Created tiles/{tile_id}/")

    # 9. Generate README.md with empty fields
    empty_tile_config = TileConfig.from_dict({})
    generate_readme(tile_id, empty_tile_config, tile_dir / "README.md")
    print(f"[create-tile] Generated README.md")

    # 10. Create works/ and runs/
    for sub in ("works/rtl", "works/tb"):
        d = tile_dir / sub
        d.mkdir(parents=True, exist_ok=True)
        (d / ".gitkeep").touch()
    print(f"[create-tile] Created works/")

    runs_dir = tile_dir / "runs"
    runs_dir.mkdir(exist_ok=True)
    (runs_dir / ".gitkeep").touch()
    print(f"[create-tile] Created runs/")

    # 11. Append row to tile_index.csv
    append_tile_index(tile_index_path, {
        "tile_number": tile_number_str,
        "tile_id": tile_id,
        "tile_name": "",
        "tile_author": "",
        "version": f"{id_version:02d}",
        "revision": f"{id_revision:02d}",
        "semicolab": "true" if project_config.semicolab else "false",
    })
    print(f"[create-tile] Appended row to tile_index.csv")

    print()
    print(f"Tile created successfully.")
    print(f"  Tile Number : {tile_number_str}")
    print(f"  Tile ID     : {tile_id}")
    print(f"  Next        : Fill in config/tile_{tile_number_str}/tile_config.yaml")
    print(f"                Add RTL to config/tile_{tile_number_str}/src/rtl/")
