from __future__ import annotations

import argparse
from pathlib import Path

from veriflow.ui.output import print_done


def cmd_generate_readme(args: argparse.Namespace) -> int:
    """Implement `veriflow project generate-readme`.

    Renders a submission README.md from the latest passing Project Mode
    run's results.json. VeriFlowError (no passing run, bad template path,
    etc.) propagates to cli.py.
    """
    from veriflow.api import generate_readme

    config_path = Path(getattr(args, "config", "veriflow.yaml"))
    out_path = getattr(args, "out", None)
    template_path = getattr(args, "template", None)

    generate_readme(config_path, out_path=out_path, template_path=template_path)

    out_display = Path(out_path) if out_path is not None else config_path.resolve().parent / "README.md"

    if not getattr(args, "non_interactive", False):
        print_done(f"README.md written -> [id]{out_display}[/id]")

    return 0
