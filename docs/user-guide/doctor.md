# `veriflow doctor` — Tool Availability Check

`veriflow doctor` verifies that the EDA tools required by VeriFlow's backends are installed
and accessible. Run it after installation and as a first troubleshooting step if `db run` or
`wrap generate` fail due to a missing tool.

---

## What it checks

| Backend category | Backend name | Tools checked |
|---|---|---|
| Connectivity | icarus | `iverilog` |
| Simulation | icarus | `iverilog`, `vvp` |
| Synthesis | yosys | `yosys` |

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

[SYNTHESIS]
  yosys
    yosys         [OK]    Yosys 0.9 (git sha1 ...)
```

Each tool line shows `[OK]` when the binary is found and reports its version, or `[FAIL]`
with an error message when the binary is not in PATH.

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
        "tools": [
          {"tool": "iverilog", "available": true, "version": "Icarus Verilog version 11.0 (stable)", "path": "/usr/bin/iverilog", "error": null}
        ]
      }
    ],
    "simulation": [
      {
        "name": "icarus",
        "tools": [
          {"tool": "iverilog", "available": true, "version": "Icarus Verilog version 11.0 (stable)", "path": "/usr/bin/iverilog", "error": null},
          {"tool": "vvp",      "available": true, "version": "Icarus Verilog runtime version 11.0 (stable)", "path": "/usr/bin/vvp", "error": null}
        ]
      }
    ],
    "synthesis": [
      {
        "name": "yosys",
        "tools": [
          {"tool": "yosys", "available": false, "version": null, "path": null, "error": "'yosys' not found in PATH"}
        ]
      }
    ]
  }
}
```

### JSON field reference

| Field | Type | Description |
|---|---|---|
| `status` | string | `"OK"` if all tools are available; `"FAIL"` if any tool is missing |
| `backends` | object | Keys: `connectivity`, `simulation`, `synthesis` |
| `backends.<category>[]` | array | One entry per backend in that category |
| `backends.<category>[].name` | string | Backend name (e.g. `"icarus"`, `"yosys"`) |
| `backends.<category>[].tools[]` | array | One entry per tool the backend requires |
| `.tools[].tool` | string | Binary name |
| `.tools[].available` | bool | `true` if the binary was found and invoked successfully |
| `.tools[].version` | string \| null | First non-empty output line from `<tool> -V`; `null` if not available |
| `.tools[].path` | string \| null | Absolute path returned by `which`; `null` if not found |
| `.tools[].error` | string \| null | Error description when `available` is `false`; `null` otherwise |

---

## Exit codes

| Code | Meaning |
|---|---|
| `0` | All tools in all backends are available |
| `1` | At least one tool is missing or could not be invoked |

---

## When to use it

- **Post-installation** — run `veriflow doctor` immediately after installing iverilog and yosys
  to confirm VeriFlow can see both tools. See [Installation](../INSTALL.md) for per-platform
  instructions.
- **Troubleshooting** — if `veriflow db run` or `veriflow wrap generate` fail with a message
  about a missing tool, run `veriflow doctor` first to identify which binary is absent before
  checking other configuration.
