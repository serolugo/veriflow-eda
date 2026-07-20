# PDK Management

VeriFlow installs and tracks PDKs (`sky130`, `gf180`, `ihp130`) itself under
`~/.veriflow/pdks/<technology name>/` — no `PDK_ROOT` or liberty path
environment variables to set by hand, and no manual download step before
synthesis will run technology-mapped.

## Quick start

```bash
veriflow pdk list                          # what's installed, and its status
veriflow pdk install sky130                # fetch and enable a PDK
veriflow pdk status                        # like list, plus full liberty paths
veriflow doctor                            # tool + PDK availability in one report
```

`sky130`/`gf180` are fetched via [volare](https://pypi.org/project/volare/)
and need the `pdks` extra:

```bash
pip install veriflow-eda[pdks]
```

`ihp130` is cloned directly from its git repository and only needs `git` in
`PATH` — no extra Python package.

If a technology's PDK isn't installed, synthesis still runs: it falls back
to generic (non-technology-mapped) synthesis and prints a
`VF_TECHNOLOGY_PDK_NOT_INSTALLED` warning instead of failing the run.

## Where to find the rest

| Topic | See |
|---|---|
| Platform-specific setup (`pdks` extra, `ihp130`'s `git` requirement) | [Installation](../INSTALL.md#pdk-installation) |
| All six subcommands in full (`install`/`update`/`status`/`versions`/`remove`/`list`), status values, per-technology `install_method`/`default_version` config | [Manual §14.8](../MANUAL.md#148-pdk-management-veriflow-pdk) |
| Selecting a technology per project (`technology:` in `veriflow.yaml`/`project_config.yaml`), external `technology.definition:` | [Project Mode Configuration](../PROJECT_CONFIG.md) |
| The `veriflow_list_pdks` MCP tool (agent-driven PDK status checks) | [MCP Server](../MCP_SERVER.md) |
