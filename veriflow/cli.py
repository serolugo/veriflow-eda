"""
VeriFlow V1 — CLI entry point

Usage:
    veriflow                           → TUI interactiva
    veriflow --db ./database init [--force]
    veriflow --db ./database create-tile
    veriflow --db ./database run --tile XXXX [options]
    veriflow --db ./database bump-version --tile XXXX
    veriflow --db ./database bump-revision --tile XXXX
"""

import argparse
import sys
from pathlib import Path

# Ensure the package root (parent of veriflow/) is in sys.path
_pkg_root = Path(__file__).resolve().parent.parent
if str(_pkg_root) not in sys.path:
    sys.path.insert(0, str(_pkg_root))

from veriflow.core import VeriFlowError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="veriflow",
        description="VeriFlow — RTL verification and documentation tool",
    )
    parser.add_argument(
        "--db",
        required=False,
        metavar="PATH",
        help="Path to the VeriFlow database directory",
    )

    sub = parser.add_subparsers(dest="command")

    # init
    p_init = sub.add_parser("init", help="Initialize a new database")
    p_init.add_argument("--force", action="store_true", help="Overwrite existing database")

    # create-tile
    sub.add_parser("create-tile", help="Create a new tile entry")

    # run
    p_run = sub.add_parser("run", help="Run the verification pipeline")
    p_run.add_argument("--tile", required=True, metavar="XXXX", help="Tile number (e.g. 0001)")
    p_run.add_argument("--skip-check",  action="store_true", help="Skip connectivity check")
    p_run.add_argument("--skip-sim",    action="store_true", help="Skip simulation")
    p_run.add_argument("--skip-synth",  action="store_true", help="Skip synthesis")
    p_run.add_argument("--only-check",  action="store_true", help="Run connectivity check only")
    p_run.add_argument("--only-sim",    action="store_true", help="Run simulation only")
    p_run.add_argument("--only-synth",  action="store_true", help="Run synthesis only")
    p_run.add_argument("--waves",       action="store_true", help="Launch waveform viewer after simulation")

    # bump-version
    p_bv = sub.add_parser("bump-version", help="Increment tile version")
    p_bv.add_argument("--tile", required=True, metavar="XXXX", help="Tile number")

    # waves
    p_waves = sub.add_parser("waves", help="Open waveform viewer for a tile run")
    p_waves.add_argument("--tile", required=True, metavar="XXXX", help="Tile number")
    p_waves.add_argument("--run",  default=None,  metavar="run-NNN", help="Run ID (default: latest)")

    # bump-revision
    p_br = sub.add_parser("bump-revision", help="Increment tile revision")
    p_br.add_argument("--tile", required=True, metavar="XXXX", help="Tile number")

    return parser


def main(argv: list[str] | None = None) -> int:
    # No arguments → TUI interactiva
    if not (argv if argv is not None else sys.argv[1:]):
        from veriflow.ui.tui import run_tui
        run_tui()
        return 0

    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.db:
        parser.print_help()
        return 1

    db = Path(args.db)

    try:
        if args.command == "init":
            from veriflow.commands.init_db import cmd_init
            cmd_init(db, force=args.force)

        elif args.command == "create-tile":
            from veriflow.commands.create_tile import cmd_create_tile
            cmd_create_tile(db)

        elif args.command == "run":
            from veriflow.commands.run import cmd_run
            cmd_run(
                db=db,
                tile_number=args.tile,
                skip_check=args.skip_check,
                skip_sim=args.skip_sim,
                skip_synth=args.skip_synth,
                only_check=args.only_check,
                only_sim=args.only_sim,
                only_synth=args.only_synth,
                waves=args.waves,
            )

        elif args.command == "bump-version":
            from veriflow.commands.bump_version import cmd_bump_version
            cmd_bump_version(db, tile_number=args.tile)

        elif args.command == "waves":
            from veriflow.commands.waves import cmd_waves
            cmd_waves(db, tile_number=args.tile, run_id=args.run)

        elif args.command == "bump-revision":
            from veriflow.commands.bump_revision import cmd_bump_revision
            cmd_bump_revision(db, tile_number=args.tile)

        else:
            parser.print_help()

    except VeriFlowError as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\n[INFO] Interrupted by user.")
        return 130

    return 0


if __name__ == "__main__":
    sys.exit(main())
