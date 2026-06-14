from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Optional


def _print_table(headers: list[str], rows: list[tuple[str, ...]]) -> None:
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(str(cell)))
    print("  " + "  ".join(h.ljust(widths[i]) for i, h in enumerate(headers)))
    print("  " + "  ".join("-" * w for w in widths))
    for row in rows:
        print("  " + "  ".join(str(cell).ljust(widths[i]) for i, cell in enumerate(row)))


def cmd_wrap_wizard(args: argparse.Namespace) -> int:
    """Interactive wrapper configuration wizard (veriflow wrap wizard).

    Uses only input()/print() for interaction (no new dependencies).
    --force allows overwriting an existing config file.
    """
    from veriflow.core.wrapper.config_template import render_wrapper_config_yaml
    from veriflow.core.wrapper.port_parser import extract_ports
    from veriflow.core.wrapper.validator import validate_mapping
    from veriflow.models.interface_profile import (
        get_interface_profile,
        list_interface_profile_names,
    )
    from veriflow.models.wrapper_config import WrapperConfig, WrapperDesign

    force: bool = getattr(args, "force", False)

    # ── Step 1: interface selection ───────────────────────────────────────────
    interface_names = list_interface_profile_names()
    if not interface_names:
        print("[ERROR] No interface profiles registered.", file=sys.stderr)
        return 1

    print()
    print("Available interfaces:")
    for i, name in enumerate(interface_names, 1):
        print(f"  {i}. {name}")
    print()

    while True:
        raw = input("Select interface [1]: ").strip() or "1"
        try:
            idx = int(raw) - 1
            if 0 <= idx < len(interface_names):
                interface_name = interface_names[idx]
                break
        except ValueError:
            pass
        print(f"  Enter a number between 1 and {len(interface_names)}.")

    interface_profile = get_interface_profile(interface_name)
    print(f"  → {interface_name} ({len(interface_profile.ports)} ports)")

    # ── Step 2: top_module and rtl_sources ───────────────────────────────────
    print()
    top_module = input("Top module name: ").strip()
    while not top_module:
        print("  Top module name is required.")
        top_module = input("Top module name: ").strip()

    module_re = re.compile(r"\bmodule\s+" + re.escape(top_module) + r"\b", re.IGNORECASE)
    source_content: Optional[str] = None
    rtl_sources: list[str] = []

    while source_content is None:
        print()
        print("RTL source files (one per line, empty line to finish):")
        rtl_sources = []
        while True:
            line = input("> ").strip()
            if not line:
                break
            rtl_sources.append(line)

        if not rtl_sources:
            print("  At least one RTL source file is required.")
            continue

        for src in rtl_sources:
            try:
                text = Path(src).read_text(encoding="utf-8")
            except OSError as e:
                print(f"  [ERROR] Cannot read {src!r}: {e}")
                continue
            if module_re.search(text):
                source_content = text
                break

        if source_content is None:
            print(f"  [ERROR] Module {top_module!r} not found in any of the provided files.")

    ip_ports = extract_ports(source_content, top_module)

    # ── Step 3: show tables ───────────────────────────────────────────────────
    print()
    print(f"Interface profile: {interface_name}")
    _print_table(
        ["Name", "Direction", "Width"],
        [(p.name, p.direction, str(p.width)) for p in interface_profile.ports],
    )

    print()
    print(f"IP ports detected in {top_module!r}:")
    _print_table(
        ["Name", "Direction", "Width"],
        [
            (name, direction, str(width) if width is not None else "?")
            for name, direction, width in ip_ports
        ],
    )

    # ── Step 4: per-port mapping ──────────────────────────────────────────────
    print()
    print("Map each IP port (press Enter to leave unmapped):")
    ports: dict[str, Optional[str]] = {}

    for ip_name, ip_dir, ip_width in ip_ports:
        width_str = str(ip_width) if ip_width is not None else "?"
        while True:
            val = input(f"  {ip_name} ({ip_dir}, {width_str}) → ").strip()
            if not val:
                ports[ip_name] = None
                break

            # Validate the full accumulated mapping including this entry.
            # Exclude None/empty entries — validate_mapping chokes on them.
            test_ports = {**ports, ip_name: val}
            valid_ports = {k: v for k, v in test_ports.items() if v}
            temp_cfg = WrapperConfig(
                interface_name=interface_name,
                metadata={},
                design=WrapperDesign(top_module=top_module, rtl_sources=rtl_sources),
                ports=valid_ports,
                wrapper_name=f"{top_module}_wrapper",
            )
            result = validate_mapping(temp_cfg, interface_profile, ip_ports)
            if result.errors:
                for e in result.errors:
                    print(f"    [ERROR] {e['code']}: {e['message']}")
                continue  # re-ask this port

            ports[ip_name] = val
            break

    # ── Step 5: final validation (robustness) ────────────────────────────────
    print()
    final_ports = {k: v for k, v in ports.items() if v is not None}
    final_cfg = WrapperConfig(
        interface_name=interface_name,
        metadata={},
        design=WrapperDesign(top_module=top_module, rtl_sources=rtl_sources),
        ports=final_ports,
        wrapper_name=f"{top_module}_wrapper",
    )
    final_result = validate_mapping(final_cfg, interface_profile, ip_ports)

    if final_result.info:
        print("  Info:")
        for msg in final_result.info:
            print(f"    {msg['code']}: {msg['message']}")
        print()

    # Robustness: if step 4 missed an error somehow, allow single-port re-maps
    while final_result.status == "FAIL":
        print("  Errors in final mapping:")
        for e in final_result.errors:
            print(f"    {e['code']}: {e['message']}")
        remap_name = input("  Port to re-map (or Enter to cancel): ").strip()
        if not remap_name:
            return 1
        port_entry = next((p for p in ip_ports if p[0] == remap_name), None)
        if port_entry is None:
            print(f"  Unknown port: {remap_name!r}")
            continue
        p_name, p_dir, p_width = port_entry
        val = input(f"  {p_name} ({p_dir}, {p_width or '?'}) → ").strip()
        ports[p_name] = val or None
        final_ports = {k: v for k, v in ports.items() if v is not None}
        final_cfg = WrapperConfig(
            interface_name=interface_name,
            metadata={},
            design=WrapperDesign(top_module=top_module, rtl_sources=rtl_sources),
            ports=final_ports,
            wrapper_name=f"{top_module}_wrapper",
        )
        final_result = validate_mapping(final_cfg, interface_profile, ip_ports)

    print(f"  Status: {final_result.status}")

    # ── Step 6: metadata ──────────────────────────────────────────────────────
    print()
    print("Metadata (press Enter for defaults):")
    meta_name = input(f"  Name [{top_module}]: ").strip() or top_module
    meta_author = input("  Author []: ").strip()
    meta_desc = input("  Description []: ").strip()
    meta_ver = input("  Version [1.0.0]: ").strip() or "1.0.0"

    default_wrapper_name = f"{top_module}_wrapper"
    wrapper_name = (
        input(f"  Wrapper name [{default_wrapper_name}]: ").strip() or default_wrapper_name
    )

    # ── Step 7: config output path ────────────────────────────────────────────
    print()
    default_config = "wrapper_config.yaml"
    while True:
        path_str = input(f"Output config file [{default_config}]: ").strip() or default_config
        config_path = Path(path_str)
        if config_path.exists() and not force:
            print(
                f"  File exists: {config_path}. "
                "Choose a different name or re-run with --force to overwrite."
            )
            continue
        break

    # ── Step 8: build config dict and write YAML ─────────────────────────────
    config_dict = {
        "interface_name": interface_name,
        "metadata": {
            "name": meta_name,
            "author": meta_author,
            "description": meta_desc,
            "version": meta_ver,
        },
        "design": {
            "top_module": top_module,
            "rtl_sources": rtl_sources,
        },
        "wrapper_name": wrapper_name,
        "ports": ports,  # includes None for unmapped ports
    }

    config_path.parent.mkdir(parents=True, exist_ok=True)
    yaml_str = render_wrapper_config_yaml(config_dict, interface_profile, ip_ports)
    config_path.write_text(yaml_str, encoding="utf-8")
    print(f"  Written: {config_path}")

    # ── Step 9: generate ──────────────────────────────────────────────────────
    print()
    import veriflow.api as _api
    gen_result = _api.wrap_generate(str(config_path))

    from veriflow.commands.wrap_generate import print_wrap_generate_result
    print_wrap_generate_result(gen_result, config_path)

    return 0 if gen_result.get("status") == "PASS" else 1
