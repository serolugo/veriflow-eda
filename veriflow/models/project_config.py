from __future__ import annotations

from dataclasses import dataclass

from veriflow.core import VeriFlowError
from veriflow.models.pipeline_config import PipelineConfig, parse_optional_pipeline_section


_DEFAULT_ID_FORMAT = "{prefix}-{date}{tile_number}{version}{revision}"


@dataclass
class ProjectConfig:
    id_prefix: str
    project_name: str
    repo: str
    description: str
    interface_name: str | None = None
    id_format: str = _DEFAULT_ID_FORMAT
    shuttle_name: str = ""
    technology_name: str | None = None
    pipeline: PipelineConfig | None = None

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
            from veriflow.models.interface_profile import list_interface_profile_names
            profiles = ", ".join(repr(p) for p in list_interface_profile_names())
            raise VeriFlowError(
                "Project configuration must explicitly declare 'interface_name'.\n"
                "  Use:\n"
                f"    interface_name: {profiles}  (or another registered profile)\n"
                "    interface_name: null          for generic projects",
                code="VF_PROJECT_INTERFACE_REQUIRED",
            )

        raw_name = data.get("interface_name", None)
        if isinstance(raw_name, str):
            raw_name = raw_name.strip() or None

        raw_id_format = data.get("id_format")
        id_format = (
            raw_id_format.strip()
            if isinstance(raw_id_format, str) and raw_id_format.strip()
            else _DEFAULT_ID_FORMAT
        )

        technology_name: str | None = None
        technology_section = data.get("technology")
        if isinstance(technology_section, dict):
            raw_tech_name = technology_section.get("name")
            if isinstance(raw_tech_name, str):
                technology_name = raw_tech_name.strip() or None

        # Raises VF_PIPELINE_CONFIG_INVALID / VF_PIPELINE_STAGE_UNKNOWN for a malformed
        # section. None means "not set here" -- DatabaseWorkflow falls back to
        # tile_config.yaml's pipeline, then to DEFAULT_PIPELINE.
        pipeline = parse_optional_pipeline_section(data)

        return cls(
            id_prefix=data.get("id_prefix", "") or "",
            project_name=data.get("project_name", "") or "",
            repo=data.get("repo", "") or "",
            description=data.get("description", "") or "",
            interface_name=raw_name,
            id_format=id_format,
            shuttle_name=data.get("shuttle_name", "") or "",
            technology_name=technology_name,
            pipeline=pipeline,
        )
