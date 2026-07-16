"""
VeriFlow V1 — CLI entry point

Usage:
    veriflow                                       → shows help
    veriflow db init --db ./database [--force]
    veriflow db create-tile --db ./database
    veriflow db run --db ./database --tile XXXX [options]
    veriflow db waves --db ./database --tile XXXX
    veriflow db bump-version --db ./database --tile XXXX
    veriflow db bump-revision --db ./database --tile XXXX
    veriflow project init [--config veriflow.yaml] [--force]
    veriflow project run --config veriflow.yaml
    veriflow project import --db ./database [--config veriflow.yaml] [--run run-NNN]
    veriflow wrap init --interface <name> --top <rtl_file>
    veriflow wrap generate --config wrapper_config.yaml
    veriflow wrap wizard
    veriflow doctor
    veriflow pdk list
    veriflow pdk install <name>
    veriflow pdk update <name>
    veriflow pdk status
"""

import argparse
import contextlib
import json
import sys
from pathlib import Path

# Ensure the package root (parent of veriflow/) is in sys.path
_pkg_root = Path(__file__).resolve().parent.parent
if str(_pkg_root) not in sys.path:
    sys.path.insert(0, str(_pkg_root))

from veriflow import __homepage__
from veriflow.core import VeriFlowError
from veriflow.ui.output import print_cli_error


def _emit_json(data: dict) -> None:
    """Write a JSON object to stdout. Called only in --json mode."""
    sys.stdout.write(json.dumps(data, indent=2) + "\n")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="veriflow",
        description="VeriFlow — RTL verification and documentation tool",
        epilog=(
            "New here? Run 'veriflow project init' in an empty directory to get started, "
            f"then 'veriflow doctor' to check required tools.\nDocs: {__homepage__}"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--json",
        action="store_true",
        default=False,
        help="Emit machine-readable JSON to stdout (suppresses human-readable output)",
    )
    parser.add_argument(
        "--non-interactive",
        action="store_true",
        default=False,
        dest="non_interactive",
        help="Disable TUI and waveform viewer; suitable for CI, scripts, and agent use",
    )

    sub = parser.add_subparsers(dest="command")

    # project (Project Mode — does not require --db)
    p_project = sub.add_parser("project", help="Project Mode commands")
    project_sub = p_project.add_subparsers(dest="project_command")
    p_project_run = project_sub.add_parser("run", help="Run a project workflow")
    p_project_run.add_argument(
        "--config",
        default="veriflow.yaml",
        metavar="PATH",
        help="Path to project config file (default: veriflow.yaml)",
    )

    p_project_init = project_sub.add_parser("init", help="Generate a commented veriflow.yaml scaffold")
    p_project_init.add_argument("--config", default="veriflow.yaml", metavar="PATH", help="Output config file path (default: veriflow.yaml)")
    p_project_init.add_argument("--force", action="store_true", help="Overwrite config file if it already exists")

    p_project_import = project_sub.add_parser(
        "import", help="Import a verified Project Mode run into a database as a new tile"
    )
    p_project_import.add_argument("--db", required=True, metavar="PATH", help="Path to the VeriFlow database directory")
    p_project_import.add_argument(
        "--config",
        default="veriflow.yaml",
        metavar="PATH",
        help="Path to project config file (default: veriflow.yaml)",
    )
    p_project_import.add_argument(
        "--run",
        default=None,
        metavar="run-NNN",
        dest="run_id",
        help="Specific run to import (default: latest run with status PASS)",
    )

    # db (Database Mode namespace)
    p_db = sub.add_parser("db", help="Database Mode commands")
    db_sub = p_db.add_subparsers(dest="db_command")

    p_db_init = db_sub.add_parser("init", help="Initialize a new database")
    p_db_init.add_argument("--db", required=True, metavar="PATH", help="Path to the VeriFlow database directory")
    p_db_init.add_argument("--force", action="store_true", help="Overwrite existing database")

    p_db_ct = db_sub.add_parser("create-tile", help="Create a new tile entry")
    p_db_ct.add_argument("--db", required=True, metavar="PATH", help="Path to the VeriFlow database directory")
    p_db_ct.add_argument(
        "--top-module",
        default="",
        metavar="NAME",
        dest="top_module",
        help="RTL top module name (required when the interface profile needs testbench scaffolding)",
    )
    p_db_ct.add_argument(
        "--tile-author",
        default="",
        metavar="NAME",
        dest="tile_author",
        help="Tile author's full name (written into tile_config.yaml; used for the {author_initials} id_format placeholder)",
    )

    p_db_run = db_sub.add_parser("run", help="Run the verification pipeline")
    p_db_run.add_argument("--db", required=True, metavar="PATH", help="Path to the VeriFlow database directory")
    p_db_run.add_argument("--tile", required=True, metavar="XXXX", help="Tile number (e.g. 0001)")
    p_db_run.add_argument("--skip-check",  action="store_true", help="Skip connectivity check")
    p_db_run.add_argument("--skip-sim",    action="store_true", help="Skip simulation")
    p_db_run.add_argument("--skip-synth",  action="store_true", help="Skip synthesis")
    p_db_run.add_argument("--only-check",  action="store_true", help="Run connectivity check only")
    p_db_run.add_argument("--only-sim",    action="store_true", help="Run simulation only")
    p_db_run.add_argument("--only-synth",  action="store_true", help="Run synthesis only")
    p_db_run.add_argument("--waves",       action="store_true", help="Launch waveform viewer after simulation")

    p_db_waves = db_sub.add_parser("waves", help="Open waveform viewer for a tile run")
    p_db_waves.add_argument("--db", required=True, metavar="PATH", help="Path to the VeriFlow database directory")
    p_db_waves.add_argument("--tile", required=True, metavar="XXXX", help="Tile number")
    p_db_waves.add_argument("--run",  default=None,  metavar="run-NNN", help="Run ID (default: latest)")

    p_db_bv = db_sub.add_parser("bump-version", help="Increment tile version")
    p_db_bv.add_argument("--db", required=True, metavar="PATH", help="Path to the VeriFlow database directory")
    p_db_bv.add_argument("--tile", required=True, metavar="XXXX", help="Tile number")

    p_db_br = db_sub.add_parser("bump-revision", help="Increment tile revision")
    p_db_br.add_argument("--db", required=True, metavar="PATH", help="Path to the VeriFlow database directory")
    p_db_br.add_argument("--tile", required=True, metavar="XXXX", help="Tile number")

    p_db_lt = db_sub.add_parser("list-tiles", help="List all registered tiles")
    p_db_lt.add_argument("--db", required=True, metavar="PATH", help="Path to the VeriFlow database directory")

    p_db_lr = db_sub.add_parser("list-runs", help="List runs for a tile")
    p_db_lr.add_argument("--db", required=True, metavar="PATH", help="Path to the VeriFlow database directory")
    p_db_lr.add_argument("--tile", required=True, metavar="XXXX", help="Tile number (e.g. 0001)")

    p_db_sr = db_sub.add_parser("show-run", help="Show details of a specific run")
    p_db_sr.add_argument("--db", required=True, metavar="PATH", help="Path to the VeriFlow database directory")
    p_db_sr.add_argument("--tile", required=True, metavar="XXXX", help="Tile number (e.g. 0001)")
    p_db_sr.add_argument("--run", required=True, metavar="run-NNN", help="Run ID (e.g. run-001)")

    # doctor (tool availability check)
    sub.add_parser("doctor", help="Check EDA tool availability for all backends")

    # pdk (PDK management namespace)
    p_pdk = sub.add_parser("pdk", help="PDK management commands")
    pdk_sub = p_pdk.add_subparsers(dest="pdk_command")

    pdk_sub.add_parser("list", help="List all technologies and their PDK install status")

    p_pdk_install = pdk_sub.add_parser("install", help="Install a technology's PDK")
    p_pdk_install.add_argument("pdk_name", metavar="NAME", help="Technology name (e.g. sky130)")

    p_pdk_update = pdk_sub.add_parser("update", help="Update an installed PDK")
    p_pdk_update.add_argument("pdk_name", metavar="NAME", help="Technology name (e.g. sky130)")

    pdk_sub.add_parser("status", help="Show detailed PDK install status (with resolved liberty paths)")

    # wrap (wrapper generation namespace)
    p_wrap = sub.add_parser("wrap", help="Wrapper generation commands")
    wrap_sub = p_wrap.add_subparsers(dest="wrap_command")

    p_wrap_init = wrap_sub.add_parser("init", help="Scaffold a wrapper_config.yaml from RTL and interface profile")
    p_wrap_init.add_argument("--interface", required=True, metavar="NAME", dest="interface", help="Interface profile name")
    p_wrap_init.add_argument("--top", required=True, metavar="FILE", dest="rtl_file", help="RTL source file; top module name is auto-detected from its contents")
    p_wrap_init.add_argument("--config", default="wrapper_config.yaml", metavar="PATH", help="Output config file path (default: wrapper_config.yaml)")
    p_wrap_init.add_argument("--wrapper-name", default=None, metavar="NAME", dest="wrapper_name", help="Wrapper module name (default: <top_module>_wrapper)")
    p_wrap_init.add_argument("--author", default=None, metavar="NAME", help="Metadata author")
    p_wrap_init.add_argument("--description", default=None, metavar="TEXT", help="Metadata description")
    p_wrap_init.add_argument("--version", default=None, metavar="VER", dest="version", help="Metadata version")
    p_wrap_init.add_argument("--force", action="store_true", help="Overwrite config file if it already exists")

    p_wrap_gen = wrap_sub.add_parser("generate", help="Generate wrapper from wrapper_config.yaml")
    p_wrap_gen.add_argument("--config", default="wrapper_config.yaml", metavar="PATH", help="Path to wrapper_config.yaml (default: wrapper_config.yaml)")
    p_wrap_gen.add_argument("--out", default=None, metavar="PATH", help="Output directory (default: wrap_out/ relative to config file)")

    p_wrap_wizard = wrap_sub.add_parser("wizard", help="Interactive wrapper configuration wizard")
    p_wrap_wizard.add_argument(
        "--force",
        action="store_true",
        help="Overwrite config file if it already exists",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()

    if not (argv if argv is not None else sys.argv[1:]):
        parser.print_help()
        return 0
    args = parser.parse_args(argv)
    json_mode: bool = args.json
    non_interactive: bool = args.non_interactive

    # --non-interactive without a subcommand is always an error — do not launch TUI
    if non_interactive and not args.command:
        err = VeriFlowError(
            "--non-interactive requires an explicit command",
            code="VF_NON_INTERACTIVE_REQUIRES_COMMAND",
            exit_code=2,
        )
        if json_mode:
            _emit_json({"status": "ERROR", "error": err.to_dict()})
        else:
            print_cli_error(str(err))
        return err.exit_code

    # In JSON mode:
    #   • console.quiet suppresses Rich output (public API — no private attributes).
    #   • redirect_stdout(stderr) catches any plain print() calls inside commands.
    #   • JSON is written via sys.stdout.write() AFTER the redirect context exits,
    #     so it always lands on the real stdout regardless of any inner redirects.
    if json_mode:
        from veriflow.ui.output import console as _console
        _console.quiet = True

    try:
        result_payload: dict | None = None
        error_payload: dict | None = None
        exit_code = 0

        _stdout_sink = (
            contextlib.redirect_stdout(sys.stderr)
            if json_mode
            else contextlib.nullcontext()
        )

        with _stdout_sink:
            try:
                dispatched = False
                run_result: dict | None = None
                db_read_result: dict | None = None
                wrap_gen_result: dict | None = None
                doctor_result: dict | None = None
                pdk_result: dict | None = None

                if args.command == "project":
                    project_cmd = getattr(args, "project_command", None)
                    if project_cmd == "run":
                        dispatched = True
                        from veriflow.commands.run_project import cmd_run_project
                        exit_code = cmd_run_project(Path(args.config))
                    elif project_cmd == "init":
                        dispatched = True
                        from veriflow.commands.init_project import cmd_init_project
                        exit_code = cmd_init_project(args)
                    elif project_cmd == "import":
                        dispatched = True
                        from veriflow.commands.import_project import cmd_import_project
                        exit_code = cmd_import_project(args)
                    else:
                        if json_mode:
                            error_payload = {
                                "status": "ERROR",
                                "error": {
                                    "code": "VF_UNKNOWN_COMMAND",
                                    "message": "No project subcommand specified",
                                },
                            }
                        else:
                            parser.print_help()
                        exit_code = 1

                elif args.command == "db":
                    db_cmd = getattr(args, "db_command", None)
                    if db_cmd is None:
                        if json_mode:
                            error_payload = {
                                "status": "ERROR",
                                "error": {
                                    "code": "VF_UNKNOWN_COMMAND",
                                    "message": "No db subcommand specified",
                                },
                            }
                        else:
                            parser.print_help()
                        exit_code = 1
                    else:
                        db = Path(args.db).resolve()

                        if db_cmd == "init":
                            dispatched = True
                            from veriflow.commands.init_db import cmd_init
                            cmd_init(db, force=args.force)

                        elif db_cmd == "create-tile":
                            dispatched = True
                            from veriflow.commands.create_tile import cmd_create_tile
                            cmd_create_tile(db, top_module=args.top_module, tile_author=args.tile_author)

                        elif db_cmd == "run":
                            if non_interactive and args.waves:
                                raise VeriFlowError(
                                    "Waveform viewer cannot be launched in non-interactive mode",
                                    code="VF_NON_INTERACTIVE_VIEWER_DISABLED",
                                    exit_code=2,
                                )
                            dispatched = True
                            from veriflow.commands.run import cmd_run
                            run_result = cmd_run(
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

                        elif db_cmd == "waves":
                            if non_interactive:
                                raise VeriFlowError(
                                    "Waveform viewer cannot be launched in non-interactive mode",
                                    code="VF_NON_INTERACTIVE_VIEWER_DISABLED",
                                    exit_code=2,
                                )
                            dispatched = True
                            from veriflow.commands.waves import cmd_waves
                            cmd_waves(db, tile_number=args.tile, run_id=args.run)

                        elif db_cmd == "bump-version":
                            dispatched = True
                            from veriflow.commands.bump_version import cmd_bump_version
                            cmd_bump_version(db, tile_number=args.tile)

                        elif db_cmd == "bump-revision":
                            dispatched = True
                            from veriflow.commands.bump_revision import cmd_bump_revision
                            cmd_bump_revision(db, tile_number=args.tile)

                        elif db_cmd == "list-tiles":
                            dispatched = True
                            from veriflow.commands.db_read import cmd_db_list_tiles, tile_info_to_dict
                            _tiles = cmd_db_list_tiles(db)
                            db_read_result = {"tiles": [tile_info_to_dict(t) for t in _tiles]}

                        elif db_cmd == "list-runs":
                            dispatched = True
                            from veriflow.commands.db_read import cmd_db_list_runs, run_info_to_dict
                            _runs = cmd_db_list_runs(db, tile=args.tile)
                            db_read_result = {"runs": [run_info_to_dict(r) for r in _runs]}

                        elif db_cmd == "show-run":
                            dispatched = True
                            from veriflow.commands.db_read import cmd_db_show_run
                            _show = cmd_db_show_run(db, run_id=args.run, tile=args.tile)
                            db_read_result = {"run": _show.to_dict()}

                elif args.command == "wrap":
                    wrap_cmd = getattr(args, "wrap_command", None)
                    if wrap_cmd is None:
                        if json_mode:
                            error_payload = {
                                "status": "ERROR",
                                "error": {
                                    "code": "VF_UNKNOWN_COMMAND",
                                    "message": "No wrap subcommand specified",
                                },
                            }
                        else:
                            parser.print_help()
                        exit_code = 1
                    elif wrap_cmd == "init":
                        dispatched = True
                        from veriflow.commands.wrap_init import cmd_wrap_init
                        exit_code = cmd_wrap_init(args)
                    elif wrap_cmd == "generate":
                        dispatched = True
                        from veriflow.commands.wrap_generate import cmd_wrap_generate
                        exit_code, wrap_gen_result = cmd_wrap_generate(args)
                    elif wrap_cmd == "wizard":
                        if non_interactive:
                            raise VeriFlowError(
                                "wrap wizard requires interactive mode; "
                                "use wrap init + wrap generate for non-interactive workflows",
                                code="VF_WIZARD_NOT_INTERACTIVE",
                                exit_code=2,
                            )
                        dispatched = True
                        from veriflow.commands.wrap_wizard import cmd_wrap_wizard
                        exit_code = cmd_wrap_wizard(args)

                elif args.command == "doctor":
                    dispatched = True
                    from veriflow.commands.doctor import cmd_doctor
                    exit_code, doctor_result = cmd_doctor(args)

                elif args.command == "pdk":
                    pdk_cmd = getattr(args, "pdk_command", None)
                    if pdk_cmd is None:
                        if json_mode:
                            error_payload = {
                                "status": "ERROR",
                                "error": {
                                    "code": "VF_UNKNOWN_COMMAND",
                                    "message": "No pdk subcommand specified",
                                },
                            }
                        else:
                            parser.print_help()
                        exit_code = 1
                    elif pdk_cmd == "list":
                        dispatched = True
                        from veriflow.commands.pdk import cmd_pdk_list
                        exit_code, pdk_result = cmd_pdk_list(args)
                    elif pdk_cmd == "status":
                        dispatched = True
                        from veriflow.commands.pdk import cmd_pdk_status
                        exit_code, pdk_result = cmd_pdk_status(args)
                    elif pdk_cmd == "install":
                        dispatched = True
                        from veriflow.commands.pdk import cmd_pdk_install
                        exit_code = cmd_pdk_install(args)
                    elif pdk_cmd == "update":
                        dispatched = True
                        from veriflow.commands.pdk import cmd_pdk_update
                        exit_code = cmd_pdk_update(args)

                else:
                    if json_mode:
                        error_payload = {
                            "status": "ERROR",
                            "error": {"code": "VF_UNKNOWN_COMMAND", "message": "No subcommand specified"},
                        }
                        exit_code = 1
                    else:
                        parser.print_help()

                if dispatched:
                    if args.command == "project":
                        result_payload = {
                            "status": "PASS" if exit_code == 0 else "FAIL",
                            "command": args.command,
                        }
                    elif args.command == "db":
                        _db_cmd = getattr(args, "db_command", None)
                        result_payload = {"status": "SUCCESS", "command": f"db {_db_cmd}"}
                        if _db_cmd == "run" and run_result is not None:
                            result_payload["run_result"] = run_result
                        elif db_read_result is not None:
                            result_payload.update(db_read_result)
                    elif args.command == "wrap":
                        _wrap_cmd = getattr(args, "wrap_command", None)
                        if _wrap_cmd == "generate" and wrap_gen_result is not None:
                            result_payload = wrap_gen_result
                        else:
                            result_payload = {"status": "SUCCESS", "command": f"wrap {_wrap_cmd}"}
                    elif args.command == "doctor":
                        result_payload = doctor_result
                    elif args.command == "pdk":
                        _pdk_cmd = getattr(args, "pdk_command", None)
                        if _pdk_cmd in ("list", "status") and pdk_result is not None:
                            result_payload = pdk_result
                        else:
                            result_payload = {
                                "status": "SUCCESS" if exit_code == 0 else "FAIL",
                                "command": f"pdk {_pdk_cmd}",
                            }

            except VeriFlowError as e:
                if json_mode:
                    error_payload = {"status": "ERROR", "error": e.to_dict()}
                else:
                    print_cli_error(str(e))
                exit_code = e.exit_code

            except KeyboardInterrupt:
                if json_mode:
                    error_payload = {
                        "status": "ERROR",
                        "error": {"code": "VF_INTERRUPTED", "message": "Interrupted by user"},
                    }
                else:
                    print("\n[INFO] Interrupted by user.")
                exit_code = 130

            except Exception as e:
                if json_mode:
                    error_payload = {
                        "status": "ERROR",
                        "error": {"code": "VF_UNHANDLED_EXCEPTION", "message": str(e)},
                    }
                    exit_code = 1
                else:
                    raise

        # Emit JSON only after the redirect context has exited, so sys.stdout
        # is the real stdout again (or the test's captured buffer).
        if json_mode:
            _emit_json(error_payload if error_payload is not None else result_payload)

        return exit_code

    finally:
        if json_mode:
            from veriflow.ui.output import console as _console
            _console.quiet = False


if __name__ == "__main__":
    sys.exit(main())
