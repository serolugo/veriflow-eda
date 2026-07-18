from __future__ import annotations

import argparse
from pathlib import Path

from veriflow.ui.output import console, print_done, print_step


def cmd_apply_spec(args: argparse.Namespace) -> int:
    """Implement `veriflow project apply-spec <spec_path>`.

    Applies a shuttle_spec.yaml's fields onto the project's veriflow.yaml.
    VeriFlowError (bad spec file, invalid interface/technology/pipeline
    value, missing veriflow.yaml, etc.) propagates to cli.py.
    """
    from veriflow.api import apply_spec

    spec_path = Path(args.spec_path)
    config_path = Path(getattr(args, "config", None)) if getattr(args, "config", None) else None

    applied = apply_spec(spec_path, config_path)

    if not getattr(args, "non_interactive", False):
        console.print()
        for field, value in applied.items():
            print_step("apply-spec", f"{field} -> {value!r}")
        print_done(f"Applied {len(applied)} field(s) from [id]{spec_path}[/id]")

    return 0
