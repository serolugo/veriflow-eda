from __future__ import annotations

import argparse

from veriflow.core.backends.registry import _CONNECTIVITY, _SIMULATION, _SYNTHESIS
from veriflow.ui.output import console


def cmd_doctor(args: argparse.Namespace) -> tuple[int, dict]:
    """Implement `veriflow doctor`.

    Returns (exit_code, result_dict). exit_code is 0 if all tools are
    available, 1 if any are missing.
    """
    categories = [
        ("connectivity", _CONNECTIVITY),
        ("simulation",   _SIMULATION),
        ("synthesis",    _SYNTHESIS),
    ]

    all_ok = True
    report: dict = {"status": None, "backends": {}}

    for category_name, registry in categories:
        category_backends: list[dict] = []
        for backend_name, backend_cls in registry.items():
            backend = backend_cls()
            tools = backend.check_availability()
            category_backends.append({"name": backend_name, "tools": tools})
            if any(not t["available"] for t in tools):
                all_ok = False
        report["backends"][category_name] = category_backends

    report["status"] = "OK" if all_ok else "FAIL"
    _print_report(report)
    return (0 if all_ok else 1), report


def _print_report(report: dict) -> None:
    for category_name, backends in report["backends"].items():
        console.print(f"\n\\[{category_name.upper()}]")
        for backend_info in backends:
            console.print(f"  {backend_info['name']}")
            for t in backend_info["tools"]:
                if t["available"]:
                    marker = "[pass]\\[OK][/pass]  "
                else:
                    marker = "[fail]\\[FAIL][/fail]"
                detail = t["version"] if t["available"] else t["error"]
                console.print(f"    {t['tool']:<12}  {marker}  {detail or ''}")
    console.print()
