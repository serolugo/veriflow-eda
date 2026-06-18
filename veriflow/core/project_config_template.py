"""project_config_template.py -- renders a commented veriflow.yaml scaffold.

Internal module; called directly by cmd_init_project.
"""

from __future__ import annotations

_SCAFFOLD = """\
# VeriFlow Project Mode configuration.
# See docs/PROJECT_CONFIG.md for the full schema reference.
# Only `design` is required -- every other section may be omitted.

design:
  top_module: ""        # required -- name of the RTL top module
  rtl_sources: []       # required -- list of RTL source file paths,
                        # relative to this file's directory
  # tb_sources: []      # optional -- testbench sources; only needed
                        # for simulation

# interface:
#   name: ""            # optional -- registered interface profile name
#                       # (e.g. "semicolab"); omit for a generic project
#                       # with no connectivity check

# execution:
#   connectivity_backend: icarus
#   simulation_backend: icarus
#   synthesis_backend: yosys

# technology:
#   name: generic

# simulation:
#   tb_top: ""          # required if tb_sources is set

# output:
#   runs_dir: runs
"""


def render_project_config_yaml() -> str:
    """Return a human-editable veriflow.yaml scaffold string."""
    return _SCAFFOLD
