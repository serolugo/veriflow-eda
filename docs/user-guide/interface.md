# Interface Profiles

An interface profile is a named port contract that the connectivity check
verifies your RTL against. VeriFlow ships one built-in profile
(`semicolab`, the nine-port Semicolab structural contract), but a project
isn't limited to it — connectivity checking is opt-in per project, not a
global mode: omit `interface:`/`interface_name:` entirely for a generic
project with no connectivity check.

## Selecting a profile

```yaml
# veriflow.yaml (Project Mode)
interface:
  name: semicolab
```

```yaml
# project_config.yaml (Database Mode)
interface_name: "semicolab"   # or null for a generic project
```

## Using your own profile — local file

Write a Verilog stub with just the port list (no body needed) and point
`definition:` at it:

```verilog
// interfaces/tinytapeout_if.v
module tinytapeout (
    input  wire       clk,
    input  wire       rst_n,
    input  wire [7:0] ui_in,
    output wire [7:0] uo_out
);
endmodule
```

```yaml
interface:
  name: tinytapeout
  definition: ./interfaces/tinytapeout_if.v   # relative to veriflow.yaml
```

`project run`/`db run` registers the profile from that file before the
connectivity stage — no code change, no restart.

## Using your own profile — a URL

`definition:` also accepts an `http://`/`https://` URL, resolved through a
**permanent local cache** (fetched once, read from
`~/.veriflow/interfaces/cache/` forever after — no repeated network
access):

```yaml
interface:
  name: tinytapeout
  definition: https://raw.githubusercontent.com/example/repo/main/tinytapeout_if.v
```

```bash
veriflow interface update tinytapeout   # force re-download, overwrite the cache
veriflow interface list-cached          # show every cached URL, profile name, download date
```

Only `http`/`https` are accepted — any other scheme (`file://`, `ftp://`,
etc.) is rejected. Only use URLs you trust: VeriFlow parses the fetched
file as a Verilog module declaration and nothing else (no code execution),
but a malicious file could still be crafted to pass a connectivity check it
shouldn't.

## Where to find the rest

| Topic | See |
|---|---|
| Full schema reference, error codes (`VF_INTERFACE_URL_SCHEME_NOT_ALLOWED`, `VF_INTERFACE_UPDATE_NOT_FOUND`, ...), Database Mode's `interface_definition:` equivalent | [Project Mode Configuration](../PROJECT_CONFIG.md) |
| Built-in profile file layout (`interface.v`/`tb_template.v`/`meta.yaml`), name-mismatch/overwrite warnings | [Manual §14.6](../MANUAL.md#146-custom-interface-profiles-interfacedefinition) |
| Generating a wrapper that adapts existing RTL to an interface profile | [Wrap](wrap.md) |
| The `veriflow_list_interface_profiles`/`veriflow_project_set` MCP tools | [MCP Server](../MCP_SERVER.md) |
