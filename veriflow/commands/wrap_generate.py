from __future__ import annotations

import argparse
from pathlib import Path

from veriflow.ui.output import console, print_status


def print_wrap_generate_result(result: dict, config_path: Path | str) -> None:
    """Print a human-readable summary of a wrap generate result dict.

    Shared by cmd_wrap_generate and cmd_wrap_wizard.
    """
    val_status = result.get("validation", {}).get("status", "FAIL")
    conn = result.get("connectivity_check")
    conn_status = conn["status"] if conn else "N/A"
    root_status = result.get("status", "FAIL")

    console.print()
    console.print(f"  [secondary]Config    [/secondary]  [id]{config_path}[/id]")

    print_status("Validation", val_status)
    if conn is not None:
        print_status("Connectivity", conn_status)

    messages = result.get("messages") or []
    errors = [m for m in messages if m.get("severity") == "error"]
    infos  = [m for m in messages if m.get("severity") == "info"]

    if errors:
        console.print()
        console.print("  [secondary]Errors:[/secondary]")
        for e in errors:
            console.print(f"    [fail]{e['code']}[/fail]  {e['message']}", highlight=False)

    if infos and root_status != "FAIL":
        console.print()
        console.print("  [secondary]Info:[/secondary]")
        for i in infos:
            console.print(f"    {i['code']}  {i['message']}", highlight=False)

    wrapper_info = result.get("wrapper", {})
    console.print()
    if root_status == "PASS":
        out_file = result.get("wrapper", {}).get("file", "")
        console.print(f"  [pass]PASS[/pass]  wrapper: [id]{out_file}[/id]")
    else:
        json_name = f"{wrapper_info.get('name', 'wrapper')}.json"
        console.print(f"  [fail]FAIL[/fail]  report:  [id]{json_name}[/id]")


def cmd_wrap_generate(args: argparse.Namespace) -> tuple[int, dict | None]:
    """Implement `veriflow wrap generate`.

    Returns (exit_code, result_dict). exit_code is 0 on PASS, 1 on FAIL.
    VeriFlowError (config-level errors) propagates to the caller (cli.py).
    """
    from veriflow.api import wrap_generate

    config_path = Path(args.config)
    out_dir = Path(args.out) if getattr(args, "out", None) else None

    result = wrap_generate(config_path, out_dir)
    print_wrap_generate_result(result, config_path)

    exit_code = 0 if result.get("status") == "PASS" else 1
    return exit_code, result
