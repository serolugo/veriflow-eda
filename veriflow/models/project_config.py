from __future__ import annotations

from dataclasses import dataclass

from veriflow.core import VeriFlowError


@dataclass
class ProjectConfig:
    id_prefix: str
    project_name: str
    repo: str
    description: str
    interface_name: str | None = None

    @classmethod
    def from_dict(cls, data: dict) -> "ProjectConfig":
        has_legacy = "semicolab" in data
        has_interface = "interface_name" in data

        if has_legacy:
            raise VeriFlowError(
                "Deprecated 'semicolab' key found in project_config.yaml.\n"
                "  Migrate to the explicit interface selection:\n"
                "    semicolab: true  → interface_name: \"semicolab\"\n"
                "    semicolab: false → interface_name: null",
                code="VF_PROJECT_INTERFACE_CONFIG_LEGACY",
                details={"deprecated_key": "semicolab"},
            )

        if not has_interface:
            raise VeriFlowError(
                "Project configuration must explicitly declare 'interface_name'.\n"
                "  Use:\n"
                "    interface_name: \"semicolab\"  for Semicolab projects\n"
                "    interface_name: null          for generic projects",
                code="VF_PROJECT_INTERFACE_REQUIRED",
            )

        raw_name = data.get("interface_name", None)
        if isinstance(raw_name, str):
            raw_name = raw_name.strip() or None

        return cls(
            id_prefix=data.get("id_prefix", "") or "",
            project_name=data.get("project_name", "") or "",
            repo=data.get("repo", "") or "",
            description=data.get("description", "") or "",
            interface_name=raw_name,
        )
