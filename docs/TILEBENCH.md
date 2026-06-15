# TileBench — optional companion environment

TileBench is an optional, in-progress companion Docker environment with VeriFlow
pre-installed alongside TileWizard and a browser-based waveform viewer. It is
maintained separately from VeriFlow and targets teams that prefer a zero-install
workflow (Docker only, no local EDA tools required).

> **Note:** TileBench is specific to the SemiCoLab development context. VeriFlow
> itself is a general-purpose tool and does not require TileBench to function.

## Quick start

```bash
# Pull and launch
docker pull serolugo/tilebench:latest
.\tilebench.bat my_workspace   # Windows
./tilebench.sh  my_workspace   # Linux / macOS

# Then use VeriFlow normally inside the container
veriflow db init --db ./veriflow/my_db
veriflow db create-tile --db ./veriflow/my_db --top-module my_module
veriflow db run --db ./veriflow/my_db --tile 0001
```

TileBench mounts your workspace folder into the container — your files always
stay on your machine.

## Waveform viewer

Inside a TileBench container, set `VERIFLOW_DOCKER=1` and VeriFlow will
automatically open waveforms in Surfer WASM at `http://localhost:7681` instead
of launching a local binary:

```bash
export VERIFLOW_DOCKER=1
veriflow db run --db ./veriflow/my_db --tile 0001 --waves
```

> **Deprecated:** `SEMICOLAB_DOCKER` is an older alias for `VERIFLOW_DOCKER`
> and is still accepted as a fallback. Prefer `VERIFLOW_DOCKER` in new scripts.

## Repository

- Docker image: `serolugo/tilebench`
- Source: [github.com/serolugo/semicolab-tilebench](https://github.com/serolugo/semicolab-tilebench)
