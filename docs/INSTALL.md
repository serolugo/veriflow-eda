# EDA Tools Installation

VeriFlow requires **iverilog** (Icarus Verilog) and **yosys**, installed
independently. oss-cad-suite is not used or required.

**Optional**: `xsim` (Vivado) is an alternative simulation backend to
`iverilog` — not required, only needed if you actually select it
(`pipeline.stages[].backend: xsim` in Database Mode, `execution.simulation_backend:
xsim` in Project Mode). See "xsim (Vivado) — optional" below.

Verify the installation with:

```sh
veriflow doctor
```

---

## Linux — Debian / Ubuntu

```sh
sudo apt-get update
sudo apt-get install -y iverilog yosys
```

**Minimum versions in recent repositories:**

| Distribution     | iverilog | yosys |
|------------------|----------|-------|
| Ubuntu 22.04 LTS | 11.0     | 0.9   |
| Ubuntu 24.04 LTS | 12.0     | 0.27  |

Both versions are sufficient for VeriFlow. The Ubuntu 22.04 versions are
verified in CI (see `.github/workflows/test.yml`).

---

## macOS

```sh
brew install icarus-verilog yosys
```

Homebrew installs the latest version of both tools (iverilog 12+,
yosys 0.38+). Verified in CI on `macos-latest`.

---

## Windows

### iverilog

Recommended option — **winget** (official standalone installer):

```powershell
winget install --id Icarus.Verilog --exact --accept-source-agreements --accept-package-agreements
```

This installs the Icarus Verilog NSIS installer from
[bleyer.org/icarus](https://bleyer.org/icarus/) and adds iverilog and vvp to
the system PATH. Package available in winget: version 12.2022.06.11.

Alternative (Chocolatey):

```powershell
choco install iverilog -y
```

### yosys

The cleanest option on Windows is **MSYS2** with the prebuilt mingw64 package:

**Step 1 — Install MSYS2** (if not already installed):

```powershell
winget install --id MSYS2.MSYS2 --exact --accept-source-agreements --accept-package-agreements
```

Or download the installer from [msys2.org](https://www.msys2.org/).

**Step 2 — Install yosys from the MSYS2 terminal (MINGW64):**

```bash
pacman -S mingw-w64-x86_64-yosys
```

**Step 3 — Add the MINGW64 directory to the system PATH:**

Add `C:\msys64\mingw64\bin` to the PATH environment variable (Control
Panel → System → Environment Variables). After this, `yosys.exe` will be
available in cmd/PowerShell and for pytest.

**Version installed with this method:** yosys 0.40+ (package
`mingw-w64-x86_64-yosys` from the `mingw64` MSYS2 repository).

### Current state of the development machine

This Windows machine has iverilog 14.0 and yosys 0.63 available through
oss-cad-suite (`C:\Users\Roman\oss-cad-suite\bin\`). MSYS2 is not installed
locally; the winget+MSYS2 method is verified in CI
(`windows-latest` on GitHub Actions).

---

## xsim (Vivado) — optional

`xsim` is an alternative simulation backend to `iverilog` — not required
for VeriFlow to work, only if you select it. Setup is Vivado-specific
(add its `bin/` directory to `PATH`, permanently or per-session) and
platform-dependent enough that it's documented in full, with a validated
Windows walkthrough, in
[`CUSTOM_BACKENDS.md`'s "Setting up an already-shipped backend" section](CUSTOM_BACKENDS.md#9-setting-up-an-already-shipped-backend)
rather than duplicated here. Same verification command either way:

```sh
veriflow doctor
```

`[SIMULATION] > xsim` should show `[OK]` for `xvlog`/`xelab`/`xsim` once
set up correctly.

---

## Post-installation verification

```sh
veriflow doctor
```

Expected output with both tools available:

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

Exit code 0 indicates that all tools are available.

---

## PDK Installation

Technology mapping (`sky130`, `gf180`, `ihp130`) needs an actual PDK on disk --
VeriFlow manages this itself under `~/.veriflow/pdks/`, with no manual
`PDK_ROOT` or liberty path environment variables required.

Check what's installed:

```sh
veriflow pdk list
```

Install a PDK:

```sh
veriflow pdk install sky130
```

`sky130` and `gf180` are fetched via [volare](https://pypi.org/project/volare/)
and require the `pdks` extra:

```sh
pip install veriflow-eda[pdks]
```

`ihp130` is cloned directly from its git repository and only requires `git`
to be in PATH -- no extra Python package needed.

Update an already-installed PDK to the latest version:

```sh
veriflow pdk update sky130
```

`veriflow doctor` reports PDK install status alongside tool availability (see
its `[TECHNOLOGIES]` section); `veriflow pdk status` shows the same
information plus the full resolved liberty path for each installed PDK.

If a technology's PDK isn't installed, synthesis still runs -- it falls back
to generic (non-technology-mapped) synthesis and prints a
`VF_TECHNOLOGY_PDK_NOT_INSTALLED` warning rather than failing the run.

---

## Using a custom interface profile

VeriFlow ships one built-in interface profile (`semicolab`), but a project
isn't limited to it. To check RTL against your own port contract, write a
Verilog stub with just the port list (no body needed):

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

Then reference it from `veriflow.yaml` alongside `name:`:

```yaml
interface:
  name: tinytapeout
  definition: ./interfaces/tinytapeout_if.v  # relative to veriflow.yaml
```

`veriflow project run` registers the profile from that file and runs the
connectivity check against it, no code changes required. See
[MANUAL.md](MANUAL.md#146-custom-interface-profiles-interfacedefinition) for the full schema (including the
Database Mode equivalent, `interface_definition:` in `project_config.yaml`)
and [PROJECT_CONFIG.md](PROJECT_CONFIG.md) for the `interface` section
reference.
