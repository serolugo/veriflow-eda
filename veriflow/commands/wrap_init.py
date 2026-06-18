from __future__ import annotations

import argparse
from pathlib import Path

from veriflow.core import VeriFlowError
from veriflow.ui.output import console, print_done


def cmd_wrap_init(args: argparse.Namespace) -> int:
    """Implement `veriflow wrap init`.

    Scaffolds a wrapper_config.yaml with commented port stubs.
    Raises VeriFlowError for config-level errors (propagates to cli.py).
    Returns exit code 0 on success.
    """
    from veriflow.api import wrap_init
    from veriflow.core.wrapper.config_template import render_wrapper_config_yaml
    from veriflow.models.interface_profile import get_interface_profile

    config_path = Path(getattr(args, "config", "wrapper_config.yaml"))
    force: bool = getattr(args, "force", False)

    if config_path.exists() and not force:
        raise VeriFlowError(
            f"Config file already exists: {config_path}\n"
            "  Use --force to overwrite.",
            code="VF_WRAP_E_CONFIG_EXISTS",
        )

    metadata: dict = {}
    for key in ("author", "description", "version"):
        val = getattr(args, key, None)
        if val:
            metadata[key] = val

    config = wrap_init(
        interface_name=args.interface,
        rtl_file=args.rtl_file,
        wrapper_name=getattr(args, "wrapper_name", None),
        metadata=metadata or None,
    )

    ip_ports = config.pop("_ip_ports")
    top_module = config["design"]["top_module"]
    interface_profile = get_interface_profile(args.interface)

    yaml_str = render_wrapper_config_yaml(config, interface_profile, ip_ports)
    config_path.write_text(yaml_str, encoding="utf-8")

    # ── Presentation ──────────────────────────────────────────────────────────
    console.print()
    console.print(
        f"  [secondary]Interface  [/secondary]  [id]{interface_profile.name}[/id]"
        f"  ({len(interface_profile.ports)} ports)"
    )
    console.print(
        f"  [secondary]Top module [/secondary]  [id]{top_module}[/id]"
        "  [secondary](auto-detected)[/secondary]"
    )
    console.print()

    if ip_ports:
        console.print("  [secondary]IP ports detected:[/secondary]")
        for name, direction, width in ip_ports:
            width_str = str(width) if width is not None else "?"
            console.print(f"    [id]{name}[/id]  {direction}, {width_str}")
    else:
        console.print("  [secondary](no ports detected in top module)[/secondary]")

    console.print()
    print_done(f"Wrote [id]{config_path}[/id]  -- fill in the ports section")

    return 0
