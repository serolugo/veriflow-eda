from __future__ import annotations

import argparse
from pathlib import Path

from veriflow.core import VeriFlowError
from veriflow.ui.output import console, print_done


def cmd_init_project(args: argparse.Namespace) -> int:
    """Implement `veriflow project init`.

    Writes a commented veriflow.yaml scaffold. The user fills in
    design.top_module and design.rtl_sources before running.
    Returns exit code 0 on success.
    """
    from veriflow.core.project_config_template import render_project_config_yaml

    config_path = Path(getattr(args, "config", "veriflow.yaml"))
    force: bool = getattr(args, "force", False)

    if config_path.exists() and not force:
        raise VeriFlowError(
            f"Config file already exists: {config_path}\n"
            "  Use --force to overwrite.",
            code="VF_PROJECT_CONFIG_EXISTS",
        )

    yaml_str = render_project_config_yaml()
    config_path.write_text(yaml_str, encoding="utf-8")

    console.print()
    print_done(f"Wrote [id]{config_path}[/id]")
    console.print(
        "  Fill in [id]design.top_module[/id] and [id]design.rtl_sources[/id]"
        " before running [id]veriflow project run[/id].\n"
    )

    return 0
