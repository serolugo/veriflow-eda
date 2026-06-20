# `veriflow wrap` — Interface Wrapper Generator

`veriflow wrap` generates a Verilog adapter wrapper that connects a generic RTL module to
a named interface profile — the same profiles used by the connectivity check. Use it when
you have existing RTL with its own port names and widths and need to plug it into a
Semicolab (or other profile) harness without modifying the original source.

The workflow produces a `wrapper.v` file that instantiates your module internally and
presents the interface profile's port signature to the outside world. After generation,
VeriFlow automatically runs the connectivity check on the wrapper to confirm it elaborates
correctly against the profile.

The three commands in this namespace are:

| Command | What it does |
|---|---|
| `wrap init` | Reads your RTL, lists ports from both sides, scaffolds `wrapper_config.yaml` |
| `wrap generate` | Reads the completed config, validates the mapping, generates the wrapper |
| `wrap wizard` | Interactive session that does both steps in one guided flow |

---

## `veriflow wrap init`

```bash
veriflow wrap init --interface <name> --top <rtl_file> \
    [--config PATH] [--wrapper-name NAME] \
    [--author AUTHOR] [--description DESC] [--version VER] \
    [--force]
```

| Flag | Required | Description |
|---|---|---|
| `--interface NAME` | yes | Interface profile to target (e.g. `semicolab`). Run `veriflow doctor` to see registered profiles. |
| `--top FILE` | yes | Verilog source file containing the top module. The module name is auto-detected from the file contents. |
| `--config PATH` | no | Where to write `wrapper_config.yaml`. Default: `wrapper_config.yaml` in the current directory. |
| `--wrapper-name NAME` | no | Name for the generated wrapper module. Default: `<top_module>_wrapper`. |
| `--author` | no | Written to `metadata.author` in the config. |
| `--description` | no | Written to `metadata.description` in the config. |
| `--version` | no | Written to `metadata.version` in the config. Default: `"1.0.0"`. |
| `--force` | no | Overwrite an existing `wrapper_config.yaml` without prompting. |

`wrap init` does not generate the wrapper -- it produces a `wrapper_config.yaml` with the
port mapping section pre-populated with the IP ports it extracted and the interface profile
ports listed as comments for reference. Open the file, fill in the mapping, then run
`wrap generate`.

The command prints the detected module name so you can confirm it is correct before
editing the config.

### Auto-detection limit

`--top` must point to a file that contains **exactly one** `module` declaration.

- **File not found** (`VF_WRAP_RTL_FILE_NOT_FOUND`): the path given to `--top` does not
  exist. Check the path and try again.
- **Zero modules found** (`VF_WRAP_E_NO_MODULE_FOUND`): the file has no `module`
  statement -- check that you passed the right file.
- **Multiple modules found** (`VF_WRAP_E_MULTIPLE_MODULES_FOUND`): the file contains
  more than one `module` declaration. This case is not supported by auto-detection.
  Move the top module to its own separate `.v` file before running `wrap init`.
  There is no flag to override this -- it is a deliberate design limit.

---

## `wrapper_config.yaml` — complete schema

```yaml
# Which interface profile to target. Must match a registered profile name.
interface_name: semicolab

metadata:
  name: my_ip              # Short identifier for this IP / wrapper (used in outputs)
  author: ""               # Optional — recorded in the JSON output
  description: ""          # Optional — recorded in the JSON output
  version: "1.0.0"         # Optional — recorded in the JSON output

design:
  top_module: my_ip        # Must match the module declaration in the source files exactly
  rtl_sources:             # List of Verilog source files for your IP (at least one)
    - src/my_ip.v
    - src/my_ip_defs.v     # Additional files (helpers, packages) can follow

# Name of the generated wrapper module (optional).
# Default: "<top_module>_wrapper"  →  my_ip_wrapper
wrapper_name: my_ip_wrapper

# Port mapping: <ip_port>: <interface_port>  or  <ip_port>: <interface_port>[hi:lo]
#
# Rules:
#   - Every key on the left must be a port that exists in the extracted RTL.
#   - Every value on the right must be a port (or a bit slice of a port) that exists
#     in the interface profile.
#   - Slices use [hi:lo] notation (e.g. csr_in[3:0] maps bits 3 down to 0).
#   - You do not need to map every IP port or every interface port — unmapped
#     ports are handled automatically (see Unmapped ports below).
#   - Two IP ports cannot map to overlapping bits of the same interface port.
ports:
  ip_clk:       clk              # full port — ip_clk connects to clk (both 1-bit)
  ip_rst_n:     arst_n           # full port
  ip_data_in:   data_reg_a       # full port — widths should match
  ip_ctrl:      csr_in[3:0]      # slice — ip_ctrl connects to bits 3:0 of csr_in
  ip_data_out:  data_reg_c       # full port
  ip_status:    csr_out[7:0]     # slice — ip_status connects to bits 7:0 of csr_out
```

All paths in `rtl_sources` are relative to the directory that contains `wrapper_config.yaml`
(same convention as `veriflow.yaml` in Project Mode).

### Unmapped ports

You are not required to map every port on both sides.

| Situation | What the wrapper does |
|---|---|
| Interface **output** port has unmapped bits | Assigns those bits to `0` (no floating nets) |
| Interface **input** port has bits not consumed by any IP port | Interface signal is present but unused inside the wrapper — this is fine |
| IP **input** port is not mapped | Port is tied to `1'b0` inside the wrapper instantiation |
| IP **output** port is not mapped | Port is left unconnected (`.port()`) inside the wrapper |

All of these situations are reported as informational messages (`VF_WRAP_I_*`) in the JSON
output — they do not cause the build to fail.

---

## `veriflow wrap generate`

```bash
veriflow wrap generate --config wrapper_config.yaml [--out DIR]
```

| Flag | Required | Description |
|---|---|---|
| `--config PATH` | yes | Path to the completed `wrapper_config.yaml`. |
| `--out DIR` | no | Output directory. Default: `wrap_out/` relative to the directory containing the config file. |

### What it validates

Before generating anything, `wrap generate` validates the port mapping. If any of the
following structural errors are found, the command exits with an error, no wrapper is
written, and a JSON file with the error details is the only output:

| What you will see | Error code (in JSON/logs) | What it means |
|---|---|---|
| config file not found | `VF_WRAP_CONFIG_NOT_FOUND` | The path given to `--config` does not exist |
| YAML parse error | `VF_WRAP_CONFIG_YAML_ERROR` | `wrapper_config.yaml` exists but contains invalid YAML |
| RTL source not found | `VF_WRAP_RTL_SOURCE_NOT_FOUND` | A path listed in `design.rtl_sources` does not exist |
| `invalid mapping syntax` | `VF_WRAP_E_MAPPING_SYNTAX` | A value in `ports:` is not a valid port name or `port[hi:lo]` slice |
| `interface port not found` | `VF_WRAP_E_INTERFACE_PORT_UNKNOWN` | The right-hand side names a port that does not exist in the chosen interface profile |
| `IP port not found` | `VF_WRAP_E_IP_PORT_UNKNOWN` | The left-hand side names a port that was not extracted from your RTL |
| `slice out of range` | `VF_WRAP_E_SLICE_OUT_OF_RANGE` | `[hi:lo]` references bits beyond the interface port width, or `hi < lo` |
| `bit conflict` | `VF_WRAP_E_BIT_CONFLICT` | Two IP ports are mapped to overlapping bits of the same interface port |

### What it generates

On validation success, `wrap generate` writes the following files to `--out` (default:
`wrap_out/` relative to the config file). All output is contained inside `out_dir` — no loose
files are written next to the config:

```
<out_dir>/                   # default: <config_dir>/wrap_out/
  <wrapper_name>.json        # result report (always written, even on failure)
  rtl/
    <basename>.v             # copy of each file listed in rtl_sources (validation PASS only)
    <wrapper_name>.v         # the generated wrapper (validation PASS only)
  logs/
    connectivity.log         # iverilog elaboration log (validation PASS only)
```

### Connectivity check

After generating the wrapper, VeriFlow compiles it against the interface profile using the
same elaboration check as `veriflow db run`. A **PASS** means the wrapper's port signature
matches the profile contract exactly. A **FAIL** means something in the generated wrapper
did not elaborate correctly — the wrapper file and the log are still written so you can
inspect the issue.

### Behavior on failure

| Failure point | Wrapper written? | RTL copied? | JSON written? | Exit code |
|---|---|---|---|---|
| Validation error (`VF_WRAP_E_*`) | No | No | Yes | Non-zero |
| Connectivity check FAIL | Yes | Yes | Yes | Non-zero |

---

## JSON output schema

```json
{
  "schema_version": "1.0",
  "status": "PASS",
  "command": "wrap generate",
  "interface_name": "semicolab",
  "wrapper": {
    "name": "my_ip_wrapper",
    "top_module": "my_ip",
    "file": "rtl/my_ip_wrapper.v"
  },
  "rtl_sources": ["rtl/my_ip.v", "rtl/my_ip_defs.v"],
  "ports": {
    "mapped": [
      {"ip_port": "ip_clk",     "interface_port": "clk",       "slice": null},
      {"ip_port": "ip_ctrl",    "interface_port": "csr_in",    "slice": "3:0"}
    ],
    "unmapped_ip_ports": ["ip_extra_out"],
    "unmapped_interface_ports": [
      {"port": "data_reg_b", "direction": "input", "bits": "31:0"}
    ]
  },
  "messages": [
    {"code": "VF_WRAP_I_IP_OUTPUT_UNMAPPED",
     "severity": "info",
     "message": "ip_extra_out is not mapped; left unconnected in wrapper"}
  ],
  "validation": {"status": "PASS"},
  "connectivity_check": {"status": "PASS", "log": "logs/connectivity.log"}
}
```

| Field | Description |
|---|---|
| `status` | Overall result: `"PASS"` only if both `validation.status` and `connectivity_check.status` are `"PASS"` |
| `wrapper.file` | Relative path (from `out_dir`) to the generated wrapper |
| `rtl_sources` | Relative paths to the RTL copies in `out_dir/rtl/` |
| `ports.mapped` | Every mapping that was applied; `"slice"` is `null` for a full-port connection, `"hi:lo"` for a bit range |
| `ports.unmapped_ip_ports` | IP ports in the config that were not mapped to any interface port |
| `ports.unmapped_interface_ports` | Interface profile bits with no IP port assigned; `"bits"` shows the unassigned range |
| `messages` | Informational notes (`VF_WRAP_I_*`) — never indicate failure, just what was auto-handled |
| `validation` | Result of the structural mapping check; FAIL here means no wrapper was written |
| `connectivity_check` | Result of the iverilog elaboration check on the wrapper; `null` if validation failed |

---

## `veriflow wrap wizard`

```bash
veriflow wrap wizard [--force]
```

The wizard runs an interactive session that guides you through the complete workflow — from
choosing the interface profile to mapping ports one by one — and writes the
`wrapper_config.yaml` and runs `generate` automatically at the end.

**Session flow:**

1. Choose an interface profile from the list of registered profiles.
2. Enter the path(s) to your RTL source files. If the top module is not found, the wizard
   asks you to try different files (the session does not restart from the beginning).
3. Enter the top module name.
4. Map each extracted IP port interactively. For each port the wizard shows its direction
   and width alongside the available interface profile ports. Invalid input (wrong name,
   bad slice, conflicts) is rejected immediately with a short error message and you are
   asked to re-enter that port — the rest of your work is preserved.
5. After all ports are mapped (or skipped), the wizard asks where to save the config.
   If a file already exists at that path, it loops back to ask for a new path (unless
   `--force` was passed, in which case it overwrites without prompting).
6. Writes `wrapper_config.yaml` and runs `wrap generate` automatically.

| Flag | Description |
|---|---|
| `--force` | Overwrite an existing config file at the chosen path without prompting |

`wrap wizard` requires an interactive terminal. Running it with `--non-interactive` exits
immediately with error code `VF_WIZARD_NOT_INTERACTIVE`. Use `wrap init` + `wrap generate`
for non-interactive workflows (CI, scripts).

### Wizard vs `init` + `generate`

| | `wrap wizard` | `wrap init` + `wrap generate` |
|---|---|---|
| **Best for** | First-time use, exploratory mapping, quick prototyping | Reproducible workflows, CI, scripting, config in version control |
| **Port feedback** | Immediate — errors are caught and retried in the session | After running `generate` |
| **Config file** | Written at the end of the session | Written by `init`, edited manually, then run through `generate` |
| **Automation** | Not suitable (requires interactive input) | Suitable — `generate` is scriptable |

---

## End-to-end example

This example wraps an 8-bit counter into the Semicolab interface profile.

### 1. The RTL module

```verilog
// counter8.v
`timescale 1ns / 1ps
module counter8 (
    input  wire       clk,
    input  wire       rst_n,
    input  wire       enable,
    output wire [7:0] count_out
);
    reg [7:0] count;
    assign count_out = count;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n)
            count <= 8'd0;
        else if (enable)
            count <= count + 8'd1;
    end
endmodule
```

### 2. Scaffold the config

```bash
veriflow wrap init --interface semicolab --top counter8.v \
    --wrapper-name counter8_wrapper
```

This creates `wrapper_config.yaml` with the IP ports extracted and the interface profile
ports listed as comments. The `ports:` section is empty — each key is the IP port name and
the value needs to be filled in:

```yaml
interface_name: semicolab

metadata:
  name: counter8
  author: ""
  description: ""
  version: "1.0.0"

design:
  top_module: counter8
  rtl_sources:
    - counter8.v

wrapper_name: counter8_wrapper

ports:
  # Interface profile: semicolab
  # Syntax: <ip_port>: <interface_port>  or  <ip_port>: <interface_port>[hi:lo]
  #
  # IP ports (counter8):
  #   clk         input   1
  #   rst_n       input   1
  #   enable      input   1
  #   count_out   output  8
  #
  # Interface ports (semicolab):
  #   clk         input   1
  #   arst_n      input   1
  #   csr_in      input   16
  #   data_reg_a  input   32
  #   data_reg_b  input   32
  #   data_reg_c  output  32
  #   csr_out     output  16
  #   csr_in_re   output  1
  #   csr_out_we  output  1
  clk:          # input, 1
  rst_n:        # input, 1
  enable:       # input, 1
  count_out:    # output, 8
```

### 3. Fill in the mapping

Edit `wrapper_config.yaml` and complete the `ports:` section:

```yaml
ports:
  clk:        clk             # counter clk → semicolab clk (1-bit, direct)
  rst_n:      arst_n          # counter rst_n → semicolab arst_n
  enable:     csr_in[0]       # enable driven by bit 0 of csr_in
  count_out:  data_reg_c[7:0] # 8-bit count into lower byte of data_reg_c
```

Unmapped interface ports (`data_reg_a`, `data_reg_b`, `csr_in[15:1]`, `data_reg_c[31:8]`,
`csr_out`, `csr_in_re`, `csr_out_we`) are handled automatically: output bits are driven
to `0`, input bits are left unused inside the wrapper.

### 4. Generate the wrapper

```bash
veriflow wrap generate --config wrapper_config.yaml
```

Output written to `wrap_out/` relative to the config file (use `--out DIR` to choose a different location):

```
wrap_out/
  counter8_wrapper.json
  rtl/
    counter8.v
    counter8_wrapper.v
  logs/
    connectivity.log
```

### 5. Inspect the result

```json
{
  "schema_version": "1.0",
  "status": "PASS",
  "command": "wrap generate",
  "interface_name": "semicolab",
  "wrapper": {
    "name": "counter8_wrapper",
    "top_module": "counter8",
    "file": "rtl/counter8_wrapper.v"
  },
  "rtl_sources": ["rtl/counter8.v"],
  "ports": {
    "mapped": [
      {"ip_port": "clk",       "interface_port": "clk",        "slice": null},
      {"ip_port": "rst_n",     "interface_port": "arst_n",     "slice": null},
      {"ip_port": "enable",    "interface_port": "csr_in",     "slice": "0:0"},
      {"ip_port": "count_out", "interface_port": "data_reg_c", "slice": "7:0"}
    ],
    "unmapped_ip_ports": [],
    "unmapped_interface_ports": [
      {"port": "csr_in",    "direction": "input",  "bits": "15:1"},
      {"port": "data_reg_a","direction": "input",  "bits": "31:0"},
      {"port": "data_reg_b","direction": "input",  "bits": "31:0"},
      {"port": "data_reg_c","direction": "output", "bits": "31:8"},
      {"port": "csr_out",   "direction": "output", "bits": "15:0"},
      {"port": "csr_in_re", "direction": "output", "bits": "0:0"},
      {"port": "csr_out_we","direction": "output", "bits": "0:0"}
    ]
  },
  "messages": [
    {"code": "VF_WRAP_I_INTERFACE_INPUT_UNUSED",    "severity": "info",
     "message": "csr_in[15:1] not consumed by any IP port"},
    {"code": "VF_WRAP_I_INTERFACE_INPUT_UNUSED",    "severity": "info",
     "message": "data_reg_a not consumed by any IP port"},
    {"code": "VF_WRAP_I_INTERFACE_INPUT_UNUSED",    "severity": "info",
     "message": "data_reg_b not consumed by any IP port"},
    {"code": "VF_WRAP_I_INTERFACE_OUTPUT_UNMAPPED", "severity": "info",
     "message": "data_reg_c[31:8] has no IP port mapped; assigned to 0"},
    {"code": "VF_WRAP_I_INTERFACE_OUTPUT_UNMAPPED", "severity": "info",
     "message": "csr_out not mapped; assigned to 0"},
    {"code": "VF_WRAP_I_INTERFACE_OUTPUT_UNMAPPED", "severity": "info",
     "message": "csr_in_re not mapped; assigned to 0"},
    {"code": "VF_WRAP_I_INTERFACE_OUTPUT_UNMAPPED", "severity": "info",
     "message": "csr_out_we not mapped; assigned to 0"}
  ],
  "validation": {"status": "PASS"},
  "connectivity_check": {"status": "PASS", "log": "logs/connectivity.log"}
}
```

All four counter ports are mapped (`unmapped_ip_ports` is empty). The seven informational
messages report the interface ports that were auto-handled — none of them indicate a
problem. `status: "PASS"` confirms the wrapper elaborates correctly.
