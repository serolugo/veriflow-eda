# `veriflow doctor` — Tool Availability Check

`veriflow doctor` verifies that the EDA tools required by VeriFlow's backends are installed
and accessible, and reports PDK install status for every registered technology. Run it after
installation and as a first troubleshooting step if `db run` or `wrap generate` fail due to a
missing tool or PDK.

---

## What it checks

| Backend category | Backend name | Tools checked |
|---|---|---|
| Connectivity | icarus | `iverilog` |
| Simulation | icarus | `iverilog`, `vvp` |
| Simulation | xsim (optional) | `xvlog`, `xelab`, `xsim` — Vivado, see [Custom Backends](../CUSTOM_BACKENDS.md) |
| Synthesis | yosys | `yosys` |

Plus, for every registered technology (`generic`, `sky130`, `gf180`, `ihp130`, or any external
`technology.definition:`), PDK install status via `models/pdk_manager.py` — see
[PDK Management](pdk.md).

---

## Plain-text output

```
[CONNECTIVITY]
  icarus
    iverilog      [OK]    Icarus Verilog version 11.0 (stable)

[SIMULATION]
  icarus
    iverilog      [OK]    Icarus Verilog version 11.0 (stable)
    vvp           [OK]    Icarus Verilog runtime version 11.0 (stable)
  xsim  (optional -- another backend in this category is available)
    xvlog         [FAIL]  'xvlog' not found in PATH
    xelab         [FAIL]  'xelab' not found in PATH
    xsim          [FAIL]  'xsim' not found in PATH

[SYNTHESIS]
  yosys
    yosys         [OK]    Yosys 0.9 (git sha1 ...)

[TECHNOLOGIES]
  generic       [OK]            (no PDK required)
  sky130        [OK]            0fe599b2  ~/.veriflow/pdks/sky130/sky130A/libs.ref/.../sky130_fd_sc_hd__tt_025C_1v80.lib
  gf180         [NOT INSTALLED] install with: veriflow pdk install gf180
  ihp130        [NOT INSTALLED] install with: veriflow pdk install ihp130
```

Each tool line shows `[OK]` when the binary is found and reports its version, or `[FAIL]`
with an error message when the binary is not in PATH. A backend marked `(optional -- another
backend in this category is available)` — like `xsim` above — does not affect the overall exit
code as long as at least one backend in its category (here, `icarus`) is available; see
[Exit codes](#exit-codes) below.

Each technology line shows `[OK]` (PDK installed and its liberty file resolved, or no PDK
needed), `[NOT INSTALLED]`, or `[INSTALLED, NO LIBERTY]` (the PDK directory exists but no file
matched its `liberty_glob`) — never fails the run itself, since synthesis falls back to generic
mapping when a PDK isn't installed (unless `require_pdk: true` is set on that technology).

---

## `--json` flag

```bash
veriflow doctor --json
```

Outputs a JSON object to stdout instead of the text report:

```json
{
  "status": "OK",
  "backends": {
    "connectivity": [
      {
        "name": "icarus",
        "available": true,
        "tools": [
          {"tool": "iverilog", "available": true, "version": "Icarus Verilog version 11.0 (stable)", "path": "/usr/bin/iverilog", "error": null}
        ]
      }
    ],
    "simulation": [
      {
        "name": "icarus",
        "available": true,
        "tools": [
          {"tool": "iverilog", "available": true, "version": "Icarus Verilog version 11.0 (stable)", "path": "/usr/bin/iverilog", "error": null},
          {"tool": "vvp",      "available": true, "version": "Icarus Verilog runtime version 11.0 (stable)", "path": "/usr/bin/vvp", "error": null}
        ]
      },
      {
        "name": "xsim",
        "available": false,
        "tools": [
          {"tool": "xvlog", "available": false, "version": null, "path": null, "error": "'xvlog' not found in PATH"},
          {"tool": "xelab", "available": false, "version": null, "path": null, "error": "'xelab' not found in PATH"},
          {"tool": "xsim",  "available": false, "version": null, "path": null, "error": "'xsim' not found in PATH"}
        ]
      }
    ],
    "synthesis": [
      {
        "name": "yosys",
        "available": true,
        "tools": [
          {"tool": "yosys", "available": true, "version": "Yosys 0.9 (git sha1 ...)", "path": "/usr/bin/yosys", "error": null}
        ]
      }
    ]
  },
  "technologies": [
    {"name": "generic", "status": "OK", "liberty": null, "version": null, "install_hint": null},
    {"name": "sky130",  "status": "OK", "liberty": "/home/user/.veriflow/pdks/sky130/sky130A/libs.ref/.../sky130_fd_sc_hd__tt_025C_1v80.lib", "version": "0fe599b2", "install_hint": null},
    {"name": "gf180",   "status": "NOT INSTALLED", "liberty": null, "version": null, "install_hint": "veriflow pdk install gf180"}
  ]
}
```

### JSON field reference

| Field | Type | Description |
|---|---|---|
| `status` | string | `"OK"` if every backend *category* has at least one available backend; `"FAIL"` otherwise. A missing PDK never affects this field. |
| `backends` | object | Keys: `connectivity`, `simulation`, `synthesis` |
| `backends.<category>[]` | array | One entry per backend registered for that category (e.g. `simulation` has both `icarus` and `xsim`) |
| `backends.<category>[].name` | string | Backend name (e.g. `"icarus"`, `"xsim"`, `"yosys"`) |
| `backends.<category>[].available` | bool | `true` if every tool this backend needs is available |
| `backends.<category>[].tools[]` | array | One entry per tool the backend requires |
| `.tools[].tool` | string | Binary name |
| `.tools[].available` | bool | `true` if the binary was found and invoked successfully |
| `.tools[].version` | string \| null | First non-empty output line from `<tool> -V`; `null` if not available |
| `.tools[].path` | string \| null | Absolute path returned by `which`; `null` if not found |
| `.tools[].error` | string \| null | Error description when `available` is `false`; `null` otherwise |
| `technologies[]` | array | One entry per registered technology (built-in or external `technology.definition:`) |
| `technologies[].name` | string | Technology name (e.g. `"sky130"`, `"generic"`) |
| `technologies[].status` | string | `"OK"` \| `"NOT INSTALLED"` \| `"INSTALLED, NO LIBERTY"` — see [PDK Management](pdk.md) |
| `technologies[].liberty` | string \| null | Resolved absolute liberty file path once installed; `null` otherwise |
| `technologies[].version` | string \| null | Installed PDK version (8-char hash); `null` if not installed or no PDK needed |
| `technologies[].install_hint` | string \| null | Suggested `veriflow pdk install <name>` command; `null` when already `"OK"` |

---

## Exit codes

| Code | Meaning |
|---|---|
| `0` | Every category (connectivity/simulation/synthesis) has at least one fully-available backend |
| `1` | At least one category has *no* available backend at all |

This is a category-level criterion, not a backend-level one: a category can register more than
one backend for the same role (simulation's `icarus` and `xsim` are alternatives, not both
required) — one being unavailable doesn't fail the run as long as another in the same category
works. A category with only one registered backend (synthesis's `yosys` today) has no fallback,
so its absence does fail that category. **A missing PDK never affects the exit code** — it's
reported in `technologies[]` as informational, since synthesis simply falls back to generic
(non-technology-mapped) mapping when a PDK isn't installed.

---

## When to use it

- **Post-installation** — run `veriflow doctor` immediately after installing iverilog and yosys
  to confirm VeriFlow can see both tools. See [Installation](../INSTALL.md) for per-platform
  instructions.
- **Troubleshooting** — if `veriflow db run` or `veriflow wrap generate` fail with a message
  about a missing tool, run `veriflow doctor` first to identify which binary is absent before
  checking other configuration.
- **Before selecting a technology** — if `project run`/`db run` warns
  `VF_TECHNOLOGY_PDK_NOT_INSTALLED`, check `[TECHNOLOGIES]`/`technologies[]` here to confirm
  which PDK is missing, then `veriflow pdk install <name>` (see [PDK Management](pdk.md)).
