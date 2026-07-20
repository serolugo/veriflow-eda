import re
from datetime import date
from pathlib import Path

import yaml

from veriflow.core import VeriFlowError
from veriflow.core.csv_store import append_tile_index, get_next_tile_number
from veriflow.core.path_safety import safe_join
from veriflow.core.tile_id import compute_initials, format_tile_id
from veriflow.core.validator import validate_database, validate_project_config
from veriflow.generators.readme import generate_readme
from veriflow.models.interface_profile import InterfaceProfile, get_interface_profile
from veriflow.models.project_config import ProjectConfig
from veriflow.models.technology_profile import DEFAULT_TECHNOLOGY_NAME
from veriflow.models.tile_config import DEFAULT_TB_TOP_MODULE, TileConfig
from veriflow.ui.output import console, print_done, print_step, print_warn

_VERILOG_ID_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_$]*$")


def _ports_comment(profile: InterfaceProfile | None) -> str:
    """Generate the ports: comment block for tile_config.yaml from a profile."""
    if profile is None:
        return "  # Document how your tile interfaces with your design (no interface profile selected)"
    lines = [f"  # Interface profile: {profile.name}"]
    for port in profile.ports:
        name_w = f"{port.name}[{port.width - 1}:0]" if port.width > 1 else port.name
        lines.append(f"  #   {name_w:<20}  {port.direction}")
    return "\n".join(lines)


_TILE_CONFIG_TEMPLATE = f"""\
# =============================================================================
# TILE INFORMATION  (permanent -- fill once)
# =============================================================================

tile_name: ""       # Display name for this tile
tile_author: ""     # Your full name
top_module: ""      # Must match the RTL filename exactly (e.g. adder_tile)
tb_top_module: "{DEFAULT_TB_TOP_MODULE}" # Testbench top module name (module declared in tb_tile.v)

description: |
  # What does this tile do?

ports: |
__PORTS_COMMENT__

usage_guide: |
  # How should this tile be used?

tb_description: |
  # Briefly describe your testbench approach

# pipeline:             # optional -- overrides project_config.yaml's pipeline for this tile only
#   stages:
#     - type: connectivity
#     - type: simulation
#     - type: synthesis
#   # each stage also accepts an optional `backend:` override, e.g.:
#   #   - type: synthesis
#   #     backend: yosys
#   # omitting `pipeline:` entirely inherits project_config.yaml's pipeline
#   # (or the current default if that's absent too: all three stages above, in order)

# technology:           # optional -- name is database-wide (project_config.yaml); only require_pdk can be overridden here
#   require_pdk: true    # omit to inherit project_config.yaml's require_pdk (default: false)

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


def cmd_create_tile(
    db: Path, *, top_module: str = "", tile_author: str = "", silent: bool = False
) -> dict:
    """Create a new tile entry in the database.

    top_module: RTL top module name.  Required when the selected interface
    profile has requires_top_module=True (raises VF_TILE_TOP_MODULE_REQUIRED
    when missing).  When provided, it is written into tile_config.yaml AND
    substituted into src/tb/tb_tile.v so that both artifacts share the same
    declared DUT name as a single source of truth.

    tile_author: Optional tile author name.  Written into tile_config.yaml
    when provided, and used to compute the {author_initials} placeholder for
    project_config.yaml's id_format.

    silent: Suppress all progress/summary output (used when this is called
    as a step of a larger command, e.g. `project import`, which prints its
    own summary instead).

    Returns {"tile_id": ..., "tile_number": ...} for the newly created tile.
    """
    step = (lambda *a, **k: None) if silent else lambda prefix, msg: print_step(prefix, msg)

    validate_database(db)

    # 1. Read project config
    project_cfg_path = db / "project_config.yaml"
    try:
        raw = yaml.safe_load(project_cfg_path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise VeriFlowError(
            f"YAML parse error in {project_cfg_path}:\n  {exc}",
            code="VF_DATABASE_CONFIG_YAML_ERROR",
            details={"path": str(project_cfg_path)},
        ) from exc
    project_config = ProjectConfig.from_dict(raw, root=db)
    validate_project_config(project_config)

    # 2. Resolve interface and validate top_module early — before any filesystem writes
    interface_name = project_config.interface_name
    profile = get_interface_profile(interface_name)  # raises VF_INTERFACE_UNKNOWN for unregistered names

    if profile and profile.requires_top_module:
        if not top_module or not top_module.strip():
            raise VeriFlowError(
                f"top_module is required when creating a tile with interface profile "
                f"'{interface_name}'. "
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

    # 5. Generate tile_id from project_config.id_format
    today = date.today()
    if "{short_hash}" in project_config.id_format:
        print_warn(
            "VF_ID_PLACEHOLDER_UNAVAILABLE: id_format uses {short_hash}, "
            "which is not yet available (requires a content snapshot). "
            "Substituting '000000'."
        )
    placeholders = {
        "prefix": project_config.id_prefix,
        "date": today.strftime("%y%m%d"),
        "tile_number": tile_number_str,
        "version": f"{id_version:02d}",
        "revision": f"{id_revision:02d}",
        "shuttle_name": project_config.shuttle_name,
        "interface": interface_name or "",
        "technology": project_config.technology_name or DEFAULT_TECHNOLOGY_NAME,
        "author_initials": compute_initials(tile_author),
        "short_hash": "000000",
    }
    tile_id = format_tile_id(project_config.id_format, placeholders)

    # tile_id is built from id_format + user-controlled placeholder values
    # (shuttle_name, id_prefix, tile_author-derived initials, ...) via a raw
    # str.format() with no output sanitization -- validate it resolves to a
    # real subdirectory of tiles/ before creating anything at all, not just
    # at the point tiles/<tile_id>/ itself gets created (dev-docs/SECURITY_AUDIT.md,
    # Finding #2: an id_format referencing {shuttle_name} combined with a
    # shuttle_name containing "../" could otherwise escape tiles/ entirely).
    tile_dir = safe_join(db / "tiles", tile_id)

    step("create-tile", f"Generating tile {tile_number_str} -> {tile_id}")

    # 6. Create config/tile_XXXX/
    config_tile_dir = db / "config" / f"tile_{tile_number_str}"
    config_tile_dir.mkdir(parents=True, exist_ok=True)
    step("create-tile", f"Created {config_tile_dir.relative_to(db)}")

    # 7. Write single tile_config.yaml (tile + run fields merged)
    config_text = _TILE_CONFIG_TEMPLATE.replace("__PORTS_COMMENT__", _ports_comment(profile))
    if top_module:
        config_text = config_text.replace('top_module: ""', f'top_module: "{top_module}"')
    if tile_author:
        config_text = config_text.replace('tile_author: ""', f'tile_author: "{tile_author}"')
    (config_tile_dir / "tile_config.yaml").write_text(config_text, encoding="utf-8")
    step("create-tile", "Written tile_config.yaml")

    # 8. Create src/rtl/ and src/tb/ with templates
    import shutil
    template_dir = Path(__file__).parent.parent / "template"
    for sub in ("src/rtl", "src/tb"):
        d = config_tile_dir / sub
        d.mkdir(parents=True, exist_ok=True)
        (d / ".gitkeep").touch()

    tb_dir = config_tile_dir / "src" / "tb"
    if profile and profile.tb_template:
        tb_template_path = Path(profile.tb_template)
    else:
        tb_template_path = template_dir / "tb_universal_template.v"
    if tb_template_path.exists():
        content = tb_template_path.read_text(encoding="utf-8")
        if top_module:
            content = content.replace("/* DUT_MODULE */", top_module)
        (tb_dir / "tb_tile.v").write_text(content, encoding="utf-8")
    profile_label = interface_name or "universal"
    step("create-tile", f"Created src/rtl/ and src/tb/ ({profile_label}: tb_tile.v)")

    # 9. Create tiles/<tile_id>/
    tile_dir.mkdir(parents=True, exist_ok=True)
    step("create-tile", f"Created tiles/{tile_id}/")

    # 9. Generate README.md with empty fields
    empty_tile_config = TileConfig.from_dict({})
    generate_readme(tile_id, empty_tile_config, tile_dir / "README.md")
    step("create-tile", "Generated README.md")

    # 10. Create works/ and runs/
    for sub in ("works/rtl", "works/tb"):
        d = tile_dir / sub
        d.mkdir(parents=True, exist_ok=True)
        (d / ".gitkeep").touch()
    step("create-tile", "Created works/")

    runs_dir = tile_dir / "runs"
    runs_dir.mkdir(exist_ok=True)
    (runs_dir / ".gitkeep").touch()
    step("create-tile", "Created runs/")

    # 11. Append row to tile_index.csv
    append_tile_index(tile_index_path, {
        "tile_number": tile_number_str,
        "tile_id": tile_id,
        "tile_name": "",
        "tile_author": "",
        "version": f"{id_version:02d}",
        "revision": f"{id_revision:02d}",
        "interface_name": interface_name or "",
    })
    step("create-tile", "Appended row to tile_index.csv")

    if not silent:
        print_done("Tile created successfully.")
        console.print(f"  [secondary]Tile Number[/secondary] : [id]{tile_number_str}[/id]")
        console.print(f"  [secondary]Tile ID    [/secondary] : [id]{tile_id}[/id]")
        console.print(f"  [secondary]Next       [/secondary] : Fill in [id]config/tile_{tile_number_str}/tile_config.yaml[/id]")
        console.print(f"                 Add RTL to [id]config/tile_{tile_number_str}/src/rtl/[/id]")

    return {"tile_id": tile_id, "tile_number": tile_number_str}
