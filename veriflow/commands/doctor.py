from __future__ import annotations

import argparse

from veriflow import __homepage__
from veriflow.core.backends.registry import _CONNECTIVITY, _SIMULATION, _SYNTHESIS
from veriflow.models.pdk_manager import get_liberty_path
from veriflow.models.technology_profile import get_technology_profile, list_technology_profile_names
from veriflow.ui.output import console


def _technologies_report() -> list[dict]:
    """One entry per registered technology: name, whether its liberty file is
    resolvable, and (when not) the install hint. Technologies with no
    installable PDK (install_method is None, e.g. "generic") always report
    "OK" -- see `models/pdk_manager.py`."""
    entries: list[dict] = []
    for name in list_technology_profile_names():
        technology = get_technology_profile(name)
        if technology.install_method is None:
            entries.append({"name": name, "status": "OK", "liberty": None, "install_hint": None})
            continue
        liberty_path = get_liberty_path(name)
        if liberty_path is not None:
            entries.append({"name": name, "status": "OK", "liberty": str(liberty_path), "install_hint": None})
        else:
            entries.append({
                "name": name,
                "status": "NOT INSTALLED",
                "liberty": None,
                "install_hint": technology.install_hint or f"veriflow pdk install {name}",
            })
    return entries


def cmd_doctor(args: argparse.Namespace) -> tuple[int, dict]:
    """Implement `veriflow doctor`.

    Returns (exit_code, result_dict). exit_code is 0 if all tools are
    available, 1 if any are missing. Missing PDKs are reported but do not
    affect exit_code -- synthesis falls back to generic mapping when a
    PDK isn't installed (see SynthesisStage), so it's informational, not
    a hard requirement like iverilog/yosys.
    """
    categories = [
        ("connectivity", _CONNECTIVITY),
        ("simulation",   _SIMULATION),
        ("synthesis",    _SYNTHESIS),
    ]

    all_ok = True
    report: dict = {"status": None, "backends": {}, "technologies": []}

    for category_name, registry in categories:
        category_backends: list[dict] = []
        for backend_name, backend_cls in registry.items():
            backend = backend_cls()
            tools = backend.check_availability()
            category_backends.append({"name": backend_name, "tools": tools})
            if any(not t["available"] for t in tools):
                all_ok = False
        report["backends"][category_name] = category_backends

    report["technologies"] = _technologies_report()

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

    console.print("\n\\[TECHNOLOGIES]")
    for tech in report.get("technologies", []):
        if tech["status"] == "OK":
            marker = "[pass]\\[OK][/pass]          "
            detail = tech["liberty"] or "(no PDK required)"
        else:
            marker = "[fail]\\[NOT INSTALLED][/fail]"
            detail = f"run: {tech['install_hint']}"
        console.print(f"  {tech['name']:<12}  {marker}  {detail}")

    console.print()
    if report["status"] == "FAIL":
        console.print(
            "[secondary]See[/secondary] "
            f"[link]{__homepage__}/blob/main/docs/INSTALL.md[/link] "
            "[secondary]for installation instructions.[/secondary]"
        )
        console.print()
