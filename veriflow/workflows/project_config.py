"""Project Mode workflow configuration.

The optional ``interface`` section selects a registered interface profile:

    interface:
      name: semicolab

Omitting the section (or ``interface: null`` / ``name: null``) means a
generic project with no interface/connectivity check. Built-in interface
names are discoverable through the registry APIs in
``veriflow.models.interface_profile``. Custom YAML-defined interface
definitions are future work.

The optional ``execution`` and ``technology`` sections select execution
backends and the technology target:

    execution:
      connectivity_backend: icarus
      simulation_backend: icarus
      synthesis_backend: yosys

    technology:
      name: generic

Both sections are optional. Omitting a section (or setting it to ``null``)
uses the current defaults shown above. Backend names must already be
registered in ``veriflow.core.backends.registry`` and technology names in
``veriflow.models.technology_profile`` — no new backends are introduced
here, and custom backend plugins are future work.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from veriflow.core import VeriFlowError
from veriflow.core.backends.registry import (
    get_connectivity_backend,
    get_simulation_backend,
    get_synthesis_backend,
)
from veriflow.models.execution_profile import default_execution_profile
from veriflow.models.interface_profile import (
    get_interface_profile,
    register_interface_profile_from_file,
    resolve_interface_definition,
)
from veriflow.models.pipeline_config import (
    DEFAULT_PIPELINE,
    PipelineConfig,
    parse_optional_pipeline_section,
)
from veriflow.models.technology_profile import (
    DEFAULT_TECHNOLOGY_NAME,
    get_technology_profile,
    load_and_register_technology_profile_from_file,
)

_EXECUTION_DEFAULTS = default_execution_profile()


@dataclass(frozen=True)
class ProjectInterfaceConfig:
    """Interface selection for Project Mode.

    ``name`` refers to a profile registered in
    ``veriflow.models.interface_profile``.
    """

    name: str

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise VeriFlowError(
                "interface.name must be a non-empty string",
                code="VF_INTERFACE_NAME_REQUIRED",
            )


def _parse_interface_section(
    data: dict, *, root: Path
) -> tuple[ProjectInterfaceConfig | None, list[str]]:
    """Returns (interface_config, config_warnings) -- config_warnings
    collects VF_INTERFACE_NAME_MISMATCH / VF_INTERFACE_PROFILE_OVERWRITTEN
    messages as plain strings (not `warnings.warn()`), so the caller
    (`ProjectWorkflowConfig.from_dict`) can surface them in results.json /
    CLI output instead of a raw Python UserWarning."""
    if "interface_name" in data:
        raise VeriFlowError(
            "Top-level 'interface_name' is not supported in Project Mode configuration.\n"
            "  Use the interface section instead:\n"
            "    interface:\n"
            "      name: semicolab",
            code="VF_INTERFACE_CONFIG_INVALID",
        )

    section = data.get("interface")
    if section is None:
        # omitted or `interface: null` — generic project, no interface check
        return None, []

    if not isinstance(section, dict):
        raise VeriFlowError(
            "interface section must be a mapping with a 'name' key, e.g.:\n"
            "    interface:\n"
            "      name: semicolab",
            code="VF_INTERFACE_CONFIG_INVALID",
            details={"interface": section},
        )

    unknown_keys = sorted(set(section) - {"name", "definition", "port_descriptions"})
    if unknown_keys:
        raise VeriFlowError(
            f"Unsupported keys in interface section: {', '.join(unknown_keys)}.\n"
            "  Supported keys: 'name', 'definition', 'port_descriptions'.",
            code="VF_INTERFACE_CONFIG_INVALID",
            details={"unknown_keys": unknown_keys},
        )

    if "name" not in section:
        raise VeriFlowError(
            "interface section requires a 'name', e.g.:\n"
            "    interface:\n"
            "      name: semicolab",
            code="VF_INTERFACE_NAME_REQUIRED",
        )

    raw_name = section["name"]
    if raw_name is None:
        # explicit `name: null` — generic project, no interface check
        # (a `definition:` alongside `name: null` is moot and ignored)
        return None, []
    if not isinstance(raw_name, str) or not raw_name.strip():
        raise VeriFlowError(
            "interface.name must be a non-empty string or null",
            code="VF_INTERFACE_NAME_REQUIRED",
            details={"name": raw_name},
        )
    name = raw_name.strip()

    raw_definition = section.get("definition")
    if raw_definition is not None:
        if not isinstance(raw_definition, str) or not raw_definition.strip():
            raise VeriFlowError(
                "interface.definition must be a non-empty string path",
                code="VF_INTERFACE_CONFIG_INVALID",
                details={"definition": raw_definition},
            )
        # An http(s):// URL resolves through the permanent local cache
        # (download once, reuse forever -- see resolve_interface_definition);
        # anything else is a local path, relative to `root` as before.
        definition_path = resolve_interface_definition(raw_definition.strip(), root)
        # Registers the profile from the .v file; the name actually
        # registered is the module name parsed from that file, which may
        # differ from `name:` above.
        registered_name, config_warnings = register_interface_profile_from_file(definition_path)
        if registered_name != name:
            config_warnings.append(
                f"interface.name {name!r} differs from the module name "
                f"{registered_name!r} parsed from interface.definition "
                f"({definition_path}). Using {registered_name!r}. "
                "[VF_INTERFACE_NAME_MISMATCH]"
            )
            name = registered_name
        return ProjectInterfaceConfig(name=name), config_warnings

    # Raises VF_INTERFACE_UNKNOWN for names not in the registry
    get_interface_profile(name)
    return ProjectInterfaceConfig(name=name), []


@dataclass(frozen=True)
class ProjectExecutionConfig:
    """Execution backend selection for Project Mode.

    Backend names refer to entries in ``veriflow.core.backends.registry``.
    """

    connectivity_backend: str = _EXECUTION_DEFAULTS.connectivity_backend
    simulation_backend: str = _EXECUTION_DEFAULTS.simulation_backend
    synthesis_backend: str = _EXECUTION_DEFAULTS.synthesis_backend

    def __post_init__(self) -> None:
        for key in ("connectivity_backend", "simulation_backend", "synthesis_backend"):
            value = getattr(self, key)
            if not isinstance(value, str) or not value.strip():
                raise VeriFlowError(
                    f"execution.{key} must be a non-empty string",
                    code="VF_EXECUTION_CONFIG_INVALID",
                    details={key: value},
                )


@dataclass(frozen=True)
class ProjectTechnologyConfig:
    """Technology target selection for Project Mode.

    ``name`` refers to a profile registered in
    ``veriflow.models.technology_profile``.

    ``require_pdk``, when True, makes the synthesis stage fail explicitly
    (``VF_TECHNOLOGY_PDK_REQUIRED_NOT_INSTALLED``) if the named technology's
    PDK isn't installed, instead of silently falling back to generic
    synthesis with a warning (the default, ``require_pdk: False``).
    """

    name: str = DEFAULT_TECHNOLOGY_NAME
    require_pdk: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise VeriFlowError(
                "technology.name must be a non-empty string",
                code="VF_TECHNOLOGY_CONFIG_INVALID",
                details={"name": self.name},
            )


_EXECUTION_KEYS = frozenset({
    "connectivity_backend",
    "simulation_backend",
    "synthesis_backend",
})

_BACKEND_VALIDATORS = {
    "connectivity_backend": get_connectivity_backend,
    "simulation_backend": get_simulation_backend,
    "synthesis_backend": get_synthesis_backend,
}


def _parse_execution_section(data: dict) -> ProjectExecutionConfig:
    section = data.get("execution")
    if section is None:
        # omitted or `execution: null` — current default backends
        return ProjectExecutionConfig()

    if not isinstance(section, dict):
        raise VeriFlowError(
            "execution section must be a mapping, e.g.:\n"
            "    execution:\n"
            "      connectivity_backend: icarus\n"
            "      simulation_backend: icarus\n"
            "      synthesis_backend: yosys",
            code="VF_EXECUTION_CONFIG_INVALID",
            details={"execution": section},
        )

    unknown_keys = sorted(set(section) - _EXECUTION_KEYS)
    if unknown_keys:
        raise VeriFlowError(
            f"Unsupported keys in execution section: {', '.join(unknown_keys)}.\n"
            f"  Supported keys: {', '.join(sorted(_EXECUTION_KEYS))}.",
            code="VF_EXECUTION_CONFIG_INVALID",
            details={"unknown_keys": unknown_keys},
        )

    defaults = ProjectExecutionConfig()
    values: dict[str, str] = {}
    for key, validate in _BACKEND_VALIDATORS.items():
        raw = section.get(key)
        if raw is None:
            # key omitted or `<key>: null` — current default backend
            values[key] = getattr(defaults, key)
            continue
        if not isinstance(raw, str) or not raw.strip():
            raise VeriFlowError(
                f"execution.{key} must be a non-empty string or null",
                code="VF_EXECUTION_CONFIG_INVALID",
                details={key: raw},
            )
        name = raw.strip()
        # Raises VF_BACKEND_*_UNKNOWN for names not in the registry
        validate(name)
        values[key] = name

    return ProjectExecutionConfig(**values)


def _parse_technology_section(data: dict, *, root: Path) -> ProjectTechnologyConfig:
    section = data.get("technology")
    if section is None:
        # omitted or `technology: null` — generic technology target
        return ProjectTechnologyConfig()

    if not isinstance(section, dict):
        raise VeriFlowError(
            "technology section must be a mapping with a 'name' key, e.g.:\n"
            "    technology:\n"
            "      name: generic",
            code="VF_TECHNOLOGY_CONFIG_INVALID",
            details={"technology": section},
        )

    unknown_keys = sorted(set(section) - {"name", "definition", "require_pdk"})
    if unknown_keys:
        raise VeriFlowError(
            f"Unsupported keys in technology section: {', '.join(unknown_keys)}.\n"
            "  Supported keys: 'name', 'definition', 'require_pdk'.",
            code="VF_TECHNOLOGY_CONFIG_INVALID",
            details={"unknown_keys": unknown_keys},
        )

    raw_require_pdk = section.get("require_pdk")
    if raw_require_pdk is None:
        require_pdk = False
    elif isinstance(raw_require_pdk, bool):
        require_pdk = raw_require_pdk
    else:
        raise VeriFlowError(
            "technology.require_pdk must be a boolean (true/false)",
            code="VF_TECHNOLOGY_CONFIG_INVALID",
            details={"require_pdk": raw_require_pdk},
        )

    raw_definition = section.get("definition")
    if raw_definition is not None:
        if not isinstance(raw_definition, str) or not raw_definition.strip():
            raise VeriFlowError(
                "technology.definition must be a non-empty string path",
                code="VF_TECHNOLOGY_CONFIG_INVALID",
                details={"definition": raw_definition},
            )
        definition_path = (root / raw_definition.strip()).resolve()
        # Registers the profile from the .yaml file; a relative `liberty:`
        # path inside it resolves against `root` (the veriflow.yaml
        # directory), not the process cwd.
        profile = load_and_register_technology_profile_from_file(definition_path, liberty_root=root)
        raw_name = section.get("name")
        name = profile.name
        if isinstance(raw_name, str) and raw_name.strip() and raw_name.strip() != name:
            warnings.warn(
                f"technology.name {raw_name.strip()!r} differs from the name "
                f"{name!r} declared in technology.definition ({definition_path}). "
                f"Using {name!r}. [VF_TECHNOLOGY_NAME_MISMATCH]",
                stacklevel=2,
            )
        return ProjectTechnologyConfig(name=name, require_pdk=require_pdk)

    raw_name = section.get("name")
    if raw_name is None:
        # empty section or `name: null` — generic technology target
        return ProjectTechnologyConfig(require_pdk=require_pdk)
    if not isinstance(raw_name, str) or not raw_name.strip():
        raise VeriFlowError(
            "technology.name must be a non-empty string or null",
            code="VF_TECHNOLOGY_CONFIG_INVALID",
            details={"name": raw_name},
        )

    name = raw_name.strip()
    # Raises VF_TECHNOLOGY_UNKNOWN for names not in the registry
    get_technology_profile(name)
    return ProjectTechnologyConfig(name=name, require_pdk=require_pdk)


def _parse_pipeline_section(data: dict) -> PipelineConfig:
    # omitted, or `pipeline: null` — current default: all three stages, in order.
    # Raises VF_PIPELINE_CONFIG_INVALID / VF_PIPELINE_STAGE_UNKNOWN for a malformed section.
    return parse_optional_pipeline_section(data) or DEFAULT_PIPELINE


def _parse_readme_template(data: dict, *, root: Path) -> Path | None:
    """`readme_template:` -- optional path to a custom Jinja2 template for
    `veriflow project generate-readme`, resolved relative to *root* (the
    veriflow.yaml directory). Omitted or null means "no project-level
    override" -- `generate_readme()` then falls back to VeriFlow's
    built-in default template."""
    raw = data.get("readme_template")
    if raw is None:
        return None
    if not isinstance(raw, str) or not raw.strip():
        raise VeriFlowError(
            "readme_template must be a non-empty string path or null",
            code="VF_README_TEMPLATE_INVALID",
            details={"readme_template": raw},
        )
    return (root / raw.strip()).resolve()


@dataclass
class ProjectWorkflowConfig:
    top_module: str
    rtl_sources: list[Path]
    tb_sources: list[Path]
    tb_top: str | None
    runs_dir: Path
    interface: ProjectInterfaceConfig | None = None
    execution: ProjectExecutionConfig = field(default_factory=ProjectExecutionConfig)
    technology: ProjectTechnologyConfig = field(default_factory=ProjectTechnologyConfig)
    pipeline: PipelineConfig = field(default_factory=lambda: DEFAULT_PIPELINE)
    readme_template: Path | None = None
    root: Path = field(default_factory=lambda: Path("."))
    # Config-parse-time warnings (currently: interface.definition's name
    # mismatch/profile-overwrite) -- surfaced in results.json's "warnings"
    # array and via print_warn(), not raised as Python UserWarning.
    config_warnings: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(
        cls,
        data: dict,
        *,
        root: Path,
    ) -> "ProjectWorkflowConfig":
        design = data.get("design") or {}

        top_module = (design.get("top_module") or "").strip()
        if not top_module:
            raise VeriFlowError(
                "design.top_module is required and must not be empty",
                code="VF_DESIGN_TOP_REQUIRED",
            )

        raw_rtl = design.get("rtl_sources") or []
        if not raw_rtl:
            raise VeriFlowError(
                "design.rtl_sources must not be empty",
                code="VF_DESIGN_RTL_REQUIRED",
            )
        rtl_sources = [root / p for p in raw_rtl]

        raw_tb = design.get("tb_sources") or []
        tb_sources = [root / p for p in raw_tb]

        interface, interface_warnings = _parse_interface_section(data, root=root)
        execution = _parse_execution_section(data)
        technology = _parse_technology_section(data, root=root)
        pipeline = _parse_pipeline_section(data)
        readme_template = _parse_readme_template(data, root=root)

        # simulation section
        sim_section = data.get("simulation")
        tb_top: str | None = None
        if isinstance(sim_section, dict):
            raw_tb_top = sim_section.get("tb_top")
            if raw_tb_top is not None:
                tb_top = str(raw_tb_top).strip() or None

        if tb_sources and not tb_top:
            raise VeriFlowError(
                "simulation.tb_top is required and must not be empty when tb_sources is non-empty",
                code="VF_SIM_TB_TOP_REQUIRED",
            )

        # output section
        output_section = data.get("output")
        runs_dir_val = None
        if isinstance(output_section, dict):
            runs_dir_val = output_section.get("runs_dir")

        runs_dir = root / (runs_dir_val if runs_dir_val else "runs")

        return cls(
            top_module=top_module,
            rtl_sources=rtl_sources,
            tb_sources=tb_sources,
            tb_top=tb_top,
            interface=interface,
            execution=execution,
            technology=technology,
            pipeline=pipeline,
            readme_template=readme_template,
            runs_dir=runs_dir,
            root=Path(root),
            config_warnings=interface_warnings,
        )

    @classmethod
    def from_file(
        cls,
        path: Path | str,
        *,
        validate_rtl_sources: bool = True,
    ) -> "ProjectWorkflowConfig":
        """validate_rtl_sources=False skips the rtl_sources existence/
        is-file check below -- used by callers that only need other fields
        off the live config (runs_dir, interface, technology, tb_top, ...)
        and don't actually touch the RTL files themselves, e.g.
        `project_import()` (only cares about a past run's *own* recorded
        rtl_sources in results.json, checked separately via
        VF_IMPORT_RTL_SOURCE_MISSING) and `generate_readme()` (describes a
        past run's verification facts plus the current interface/
        technology/metadata -- never reads rtl_sources at all)."""
        given = Path(path)
        path = given.resolve()
        if not path.exists():
            raise VeriFlowError(
                f"Project config not found: {path}",
                code="VF_PROJECT_CONFIG_NOT_FOUND",
                details={"path": str(path), "path_given": str(given)},
            )
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            raise VeriFlowError(
                f"YAML parse error in {path}:\n  {exc}",
                code="VF_PROJECT_CONFIG_YAML_ERROR",
                details={"path": str(path)},
            ) from exc
        if raw is None:
            raw = {}
        config = cls.from_dict(raw, root=path.parent)

        # Only checked here, not in from_dict(): from_dict() is exercised
        # directly by many tests with synthetic rtl_sources paths that are
        # never written to disk. from_file() is the real-world entry point
        # (an actual veriflow.yaml being run), where a directory or missing
        # path would otherwise surface as a raw iverilog/yosys tool error
        # deep inside the pipeline instead of a clear VeriFlow error.
        if validate_rtl_sources:
            for rtl_path in config.rtl_sources:
                if not rtl_path.is_file():
                    raise VeriFlowError(
                        f"design.rtl_sources entry is not a file: {rtl_path}\n"
                        "  Each entry must be a path to an existing RTL source "
                        "file, not a directory or a missing path.",
                        code="VF_DESIGN_RTL_SOURCE_NOT_FILE",
                        details={"path": str(rtl_path)},
                    )

        return config
