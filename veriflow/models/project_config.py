from __future__ import annotations

import warnings
from dataclasses import dataclass, field
from pathlib import Path

from veriflow.core import VeriFlowError
from veriflow.models.pipeline_config import PipelineConfig, parse_optional_pipeline_section


_DEFAULT_ID_FORMAT = "{prefix}-{date}{tile_number}{version}{revision}"

# Every top-level key project_config.yaml's parser actually reads.
# "semicolab" (legacy) is deliberately excluded -- it's handled by its own
# has_legacy check above, which raises before this set is ever consulted.
_KNOWN_TOP_LEVEL_KEYS = frozenset({
    "id_prefix", "project_name", "repo", "description",
    "interface_name", "interface_definition",
    "id_format", "shuttle_name",
    "technology", "technology_definition",
    "pipeline",
})

# Specific guidance for the one confirmed real-world mistake this check
# exists for: Project Mode's veriflow.yaml has a real `execution:` section
# (connectivity_backend/simulation_backend/synthesis_backend); Database
# Mode's project_config.yaml has no such section at all -- backend
# selection there is per-stage, via `pipeline.stages[].backend`. Writing
# `execution:` here is silently ignored with no error (unknown top-level
# keys aren't rejected, for forward-compatibility with future fields), so
# without this warning a user can configure e.g. `execution.simulation_backend:
# xsim` and have it do nothing at all, with zero indication why.
_EXECUTION_KEY_HINT = (
    "Database Mode specifies simulation backend per-stage via "
    "pipeline.stages[].backend, not a top-level execution: section. "
    "See docs/PROJECT_CONFIG.md."
)


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
    require_pdk: bool = False
    pipeline: PipelineConfig | None = None
    # Config-parse-time warnings (currently: interface_definition's name
    # mismatch/profile-overwrite) -- surfaced in the run's own results
    # data and via print_warn(), not raised as Python UserWarning.
    config_warnings: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict, *, root: Path | None = None) -> "ProjectConfig":
        """root: directory `interface_definition:` paths resolve relative to
        (the database directory containing this project_config.yaml). Only
        required when `interface_definition:` is actually present in *data*."""
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

        config_warnings: list[str] = []

        unknown_keys = sorted(set(data) - _KNOWN_TOP_LEVEL_KEYS)
        for key in unknown_keys:
            if key == "execution":
                config_warnings.append(f"Unknown key {key!r} in project_config.yaml -- {_EXECUTION_KEY_HINT}")
            else:
                config_warnings.append(
                    f"Unknown key {key!r} in project_config.yaml -- ignored. "
                    "See docs/PROJECT_CONFIG.md for the recognized project_config.yaml schema."
                )

        raw_definition = data.get("interface_definition")
        if raw_name is not None and raw_definition is not None:
            if not isinstance(raw_definition, str) or not raw_definition.strip():
                raise VeriFlowError(
                    "interface_definition must be a non-empty string path",
                    code="VF_PROJECT_INTERFACE_CONFIG_INVALID",
                    details={"interface_definition": raw_definition},
                )
            if root is None:
                raise VeriFlowError(
                    "interface_definition requires a config root to resolve against "
                    "(internal error: ProjectConfig.from_dict called without root=)",
                    code="VF_PROJECT_INTERFACE_CONFIG_INVALID",
                )
            from veriflow.models.interface_profile import (
                register_interface_profile_from_file,
                resolve_interface_definition,
            )

            # An http(s):// URL resolves through the permanent local cache
            # (download once, reuse forever); anything else is a local
            # path, relative to `root` as before.
            definition_path = resolve_interface_definition(raw_definition.strip(), Path(root))
            registered_name, register_warnings = register_interface_profile_from_file(definition_path)
            config_warnings.extend(register_warnings)
            if registered_name != raw_name:
                config_warnings.append(
                    f"interface_name {raw_name!r} differs from the module name "
                    f"{registered_name!r} parsed from interface_definition "
                    f"({definition_path}). Using {registered_name!r}. "
                    "[VF_INTERFACE_NAME_MISMATCH]"
                )
                raw_name = registered_name

        raw_id_format = data.get("id_format")
        id_format = (
            raw_id_format.strip()
            if isinstance(raw_id_format, str) and raw_id_format.strip()
            else _DEFAULT_ID_FORMAT
        )

        technology_name: str | None = None
        require_pdk = False
        technology_section = data.get("technology")
        if isinstance(technology_section, dict):
            raw_tech_name = technology_section.get("name")
            if isinstance(raw_tech_name, str):
                technology_name = raw_tech_name.strip() or None

            raw_require_pdk = technology_section.get("require_pdk")
            if raw_require_pdk is not None:
                if not isinstance(raw_require_pdk, bool):
                    raise VeriFlowError(
                        "technology.require_pdk must be a boolean (true/false)",
                        code="VF_PROJECT_TECHNOLOGY_CONFIG_INVALID",
                        details={"require_pdk": raw_require_pdk},
                    )
                require_pdk = raw_require_pdk

        raw_tech_definition = data.get("technology_definition")
        if raw_tech_definition is not None:
            if not isinstance(raw_tech_definition, str) or not raw_tech_definition.strip():
                raise VeriFlowError(
                    "technology_definition must be a non-empty string path",
                    code="VF_PROJECT_TECHNOLOGY_CONFIG_INVALID",
                    details={"technology_definition": raw_tech_definition},
                )
            if root is None:
                raise VeriFlowError(
                    "technology_definition requires a config root to resolve against "
                    "(internal error: ProjectConfig.from_dict called without root=)",
                    code="VF_PROJECT_TECHNOLOGY_CONFIG_INVALID",
                )
            from veriflow.models.technology_profile import load_and_register_technology_profile_from_file

            definition_path = (Path(root) / raw_tech_definition.strip()).resolve()
            profile = load_and_register_technology_profile_from_file(definition_path, liberty_root=Path(root))
            if technology_name and technology_name != profile.name:
                warnings.warn(
                    f"technology.name {technology_name!r} differs from the name "
                    f"{profile.name!r} declared in technology_definition ({definition_path}). "
                    f"Using {profile.name!r}. [VF_TECHNOLOGY_NAME_MISMATCH]",
                    stacklevel=2,
                )
            technology_name = profile.name

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
            require_pdk=require_pdk,
            pipeline=pipeline,
            config_warnings=config_warnings,
        )
