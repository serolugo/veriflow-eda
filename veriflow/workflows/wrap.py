"""WrapWorkflow — orchestrates veriflow wrap generate (P3 + P4 resolved)."""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Optional

import yaml

from veriflow.core import VeriFlowError
from veriflow.core.backends.base import ConnectivityBackend
from veriflow.core.backends.icarus import IcarusConnectivityBackend
from veriflow.core.wrapper.generator import generate_wrapper
from veriflow.core.wrapper.port_parser import extract_ports
from veriflow.core.wrapper.validator import validate_mapping
from veriflow.models.interface_profile import get_interface_profile
from veriflow.models.wrapper_config import WrapperConfig


def _serialize_slice(hi: Optional[int], lo: Optional[int]) -> Optional[str]:
    """Convert hi/lo to the JSON "slice" field: null | "N" | "hi:lo"."""
    if hi is None:
        return None
    if hi == lo:
        return str(hi)
    return f"{hi}:{lo}"


def _serialize_bits(hi: int, lo: int) -> str:
    """Convert hi/lo to the JSON "bits" field: always "hi:lo"."""
    return f"{hi}:{lo}"


class WrapWorkflow:

    def __init__(self, backend: ConnectivityBackend | None = None) -> None:
        self._backend: ConnectivityBackend = backend or IcarusConnectivityBackend()

    def generate(
        self,
        config_path: Path,
        out_dir: Optional[Path] = None,
    ) -> dict:
        """Run the full wrap generate pipeline.

        Loads wrapper_config.yaml, searches rtl_sources for top_module (P3),
        validates the port mapping, generates the wrapper (on PASS), copies RTL,
        runs the connectivity check, serializes hi/lo to slice/bits strings (P4),
        writes <wrapper_name>.json, and returns the full output dict.

        VeriFlowError propagates unchanged for config-level errors (including
        VF_WRAP_E_TOP_MODULE_NOT_FOUND). Validation FAIL is returned as a dict
        with status="FAIL" — it is NOT raised as an exception.
        """
        config_path = Path(config_path).resolve()
        config_dir = config_path.parent

        if not config_path.exists():
            raise VeriFlowError(
                f"Wrapper config not found: {config_path}",
                code="VF_WRAP_CONFIG_NOT_FOUND",
                details={"path": str(config_path)},
            )
        try:
            raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as exc:
            raise VeriFlowError(
                f"YAML parse error in {config_path}:\n  {exc}",
                code="VF_WRAP_CONFIG_YAML_ERROR",
                details={"path": str(config_path)},
            ) from exc
        config = WrapperConfig.from_dict(raw)

        # Resolve rtl_sources relative to config file's directory
        rtl_paths = [(config_dir / src).resolve() for src in config.design.rtl_sources]

        # P3 — search for top_module file-by-file in listed order
        module_re = re.compile(
            r"\bmodule\s+" + re.escape(config.design.top_module) + r"\b",
            re.IGNORECASE,
        )
        source_content: str | None = None
        for rp in rtl_paths:
            if not rp.exists():
                raise VeriFlowError(
                    f"RTL source not found: {rp}",
                    code="VF_WRAP_RTL_SOURCE_NOT_FOUND",
                    details={"path": str(rp), "rtl_sources": [str(p) for p in rtl_paths]},
                )
            text = rp.read_text(encoding="utf-8")
            if module_re.search(text):
                source_content = text
                break

        if source_content is None:
            raise VeriFlowError(
                f"Top module {config.design.top_module!r} not found in any rtl_source.",
                code="VF_WRAP_E_TOP_MODULE_NOT_FOUND",
                details={
                    "top_module": config.design.top_module,
                    "rtl_sources": [str(p) for p in rtl_paths],
                },
            )

        ip_ports = extract_ports(source_content, config.design.top_module)
        interface_profile = get_interface_profile(config.interface_name)
        result = validate_mapping(config, interface_profile, ip_ports)

        if out_dir is None:
            out_dir = config_dir / "wrap_out"
        out_dir = Path(out_dir).resolve()
        out_dir.mkdir(parents=True, exist_ok=True)

        # P4 — serialize hi/lo integers to slice/bits strings
        serialized_mapped = [
            {
                "ip_port": m["ip_port"],
                "interface_port": m["interface_port"],
                "slice": _serialize_slice(m["hi"], m["lo"]),
            }
            for m in result.mapped
        ]
        serialized_unmapped_iface = [
            {
                "port": u["port"],
                "direction": u["direction"],
                "bits": _serialize_bits(u["hi"], u["lo"]),
            }
            for u in result.unmapped_interface_ports
        ]
        messages = result.errors + result.info
        rtl_sources_rel = [f"rtl/{Path(src).name}" for src in config.design.rtl_sources]

        if result.status == "FAIL":
            out_doc = {
                "schema_version": "1.0",
                "status": "FAIL",
                "command": "wrap generate",
                "interface_name": config.interface_name,
                "wrapper": {
                    "name": config.wrapper_name,
                    "top_module": config.design.top_module,
                    "file": f"rtl/{config.wrapper_name}.v",
                },
                "rtl_sources": rtl_sources_rel,
                "ports": {
                    "mapped": serialized_mapped,
                    "unmapped_ip_ports": result.unmapped_ip_ports,
                    "unmapped_interface_ports": serialized_unmapped_iface,
                },
                "messages": messages,
                "validation": {"status": "FAIL"},
                "connectivity_check": None,
            }
            json_path = out_dir / f"{config.wrapper_name}.json"
            json_path.write_text(json.dumps(out_doc, indent=2), encoding="utf-8")
            return out_doc

        # Validation PASS — generate wrapper, copy RTL, run connectivity check
        wrapper_src = generate_wrapper(config, interface_profile, result, ip_ports)

        rtl_out_dir = out_dir / "rtl"
        rtl_out_dir.mkdir(parents=True, exist_ok=True)

        wrapper_path = rtl_out_dir / f"{config.wrapper_name}.v"
        wrapper_path.write_text(wrapper_src, encoding="utf-8")

        for rp in rtl_paths:
            shutil.copy2(rp, rtl_out_dir / rp.name)

        log_dir = out_dir / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        conn_log_path = log_dir / "connectivity.log"

        copied_rtl = [rtl_out_dir / rp.name for rp in rtl_paths]
        conn_status = self._backend.run_connectivity(
            rtl_files=[wrapper_path] + copied_rtl,
            interface_profile=interface_profile,
            top_module=config.wrapper_name,
            log_path=conn_log_path,
        )

        root_status = "PASS" if conn_status == "PASS" else "FAIL"
        out_doc = {
            "schema_version": "1.0",
            "status": root_status,
            "command": "wrap generate",
            "interface_name": config.interface_name,
            "wrapper": {
                "name": config.wrapper_name,
                "top_module": config.design.top_module,
                "file": f"rtl/{config.wrapper_name}.v",
            },
            "rtl_sources": rtl_sources_rel,
            "ports": {
                "mapped": serialized_mapped,
                "unmapped_ip_ports": result.unmapped_ip_ports,
                "unmapped_interface_ports": serialized_unmapped_iface,
            },
            "messages": messages,
            "validation": {"status": "PASS"},
            "connectivity_check": {
                "status": conn_status,
                "log": "logs/connectivity.log",
            },
        }
        json_path = out_dir / f"{config.wrapper_name}.json"
        json_path.write_text(json.dumps(out_doc, indent=2), encoding="utf-8")
        return out_doc
