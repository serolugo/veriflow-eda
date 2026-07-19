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

# pipeline:           # optional -- define which stages to run, and in what order
#   stages:
#     - type: connectivity
#     - type: simulation
#     - type: synthesis
#   # each stage also accepts an optional `backend:` override, e.g.:
#   #   - type: synthesis
#   #     backend: yosys
#   # omitting `pipeline:` entirely keeps the current default (all three
#   # stages above, in order)

# technology:
#   name: generic
#   require_pdk: false   # if true, fail instead of falling back to generic synthesis

# simulation:
#   tb_top: ""          # required if tb_sources is set

# output:
#   runs_dir: runs
"""


def render_project_config_yaml() -> str:
    """Return a human-editable veriflow.yaml scaffold string."""
    return _SCAFFOLD
