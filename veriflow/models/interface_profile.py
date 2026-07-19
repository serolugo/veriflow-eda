"""Interface profile models and registry.

Built-in interface profiles are loaded from ``veriflow/interfaces/<name>/`` at
first use — each subdirectory holds an ``interface.v`` port-contract stub
(parsed with the same regex-based extractor used for RTL auto-detection in
``wrap init``), an optional co-located ``tb_template.v``, and an optional
``meta.yaml`` for the two fields a `.v` file can't express
(``description``, ``requires_top_module``). Projects can also register their
own interface profile at runtime from an arbitrary `.v` file via
``register_interface_profile_from_file`` (see ``workflows/project_config.py``'s
``interface.definition`` field). Discoverable through the registry APIs
(``list_interface_profiles``, ``has_interface_profile``, …) so any frontend or
tool can enumerate them. InterfaceStage still writes historical "connectivity"
artifacts for compatibility.
"""

from __future__ import annotations

import hashlib
import re
import warnings
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Literal

import yaml

from veriflow.core import VeriFlowError
from veriflow.core.wrapper.port_parser import extract_ports

INTERFACES_DIR = Path(__file__).parent.parent / "interfaces"

# Permanent local cache for URL-sourced interface.definition:/interface_definition:
# values -- same philosophy as `veriflow pdk install` (models/pdk_manager.py's
# VERIFLOW_PDK_ROOT): fetched once, used from disk forever after, never
# re-fetched implicitly. Only `veriflow interface update <name>` re-downloads.
VERIFLOW_INTERFACES_CACHE_ROOT = Path.home() / ".veriflow" / "interfaces" / "cache"

_MODULE_RE = re.compile(r"\bmodule\s+(\w+)", re.IGNORECASE)
_URL_SCHEME_RE = re.compile(r"^([a-zA-Z][a-zA-Z0-9+.-]*)://")
_ALLOWED_URL_SCHEMES = frozenset({"http", "https"})


@dataclass(frozen=True)
class InterfacePort:
    name: str
    direction: Literal["input", "output", "inout"]
    width: int = 1

    def __post_init__(self) -> None:
        if not self.name or not self.name.strip():
            raise VeriFlowError(
                "InterfacePort name must not be empty or whitespace",
                code="VF_INTERFACE_PORT_NAME_REQUIRED",
            )
        if self.width <= 0:
            raise VeriFlowError(
                f"InterfacePort width must be greater than zero, got {self.width!r}",
                code="VF_INTERFACE_PORT_WIDTH_INVALID",
                details={"name": self.name, "width": self.width},
            )


@dataclass(frozen=True)
class InterfaceProfile:
    name: str
    ports: tuple[InterfacePort, ...]
    description: str = ""
    requires_top_module: bool = False
    tb_template: str | None = None  # path to a co-located tb_template.v; None → tb_universal_template.v
    port_descriptions: dict[str, str] | None = None  # {port_name: description}, from meta.yaml

    def __post_init__(self) -> None:
        if not self.name or not self.name.strip():
            raise VeriFlowError(
                "InterfaceProfile name must not be empty or whitespace",
                code="VF_INTERFACE_NAME_REQUIRED",
            )
        if not self.ports:
            raise VeriFlowError(
                "InterfaceProfile must define at least one port",
                code="VF_INTERFACE_PORT_REQUIRED",
            )
        seen: set[str] = set()
        for port in self.ports:
            if port.name in seen:
                raise VeriFlowError(
                    f"Duplicate port name {port.name!r} in InterfaceProfile {self.name!r}",
                    code="VF_INTERFACE_PORT_DUPLICATE",
                    details={"port": port.name, "profile": self.name},
                )
            seen.add(port.name)


def _find_module_names(text: str) -> list[str]:
    seen: set[str] = set()
    names: list[str] = []
    for name in _MODULE_RE.findall(text):
        if name not in seen:
            seen.add(name)
            names.append(name)
    return names


def load_interface_profile_from_file(path: Path) -> InterfaceProfile:
    """Load an InterfaceProfile from a Verilog port-contract stub file.

    The file needs only a `module <name> (...);` port-list declaration (an
    `endmodule` with no body is enough -- see e.g.
    `veriflow/interfaces/semicolab/interface.v`). Ports are extracted with
    `core.wrapper.port_parser.extract_ports`, the same regex-based parser
    used for RTL auto-detection in `wrap init`.

    The profile's name is the parsed module name (not the file/directory
    name). An optional `tb_template.v` in the same directory becomes
    `tb_template`; an optional `meta.yaml` in the same directory supplies
    `description`/`requires_top_module`/`port_descriptions` (description and
    requires_top_module default to `""`/`False`, port_descriptions to None,
    when absent -- a bare `.v` file with no sidecar is a complete, valid
    profile).

    Raises:
        VeriFlowError(VF_INTERFACE_FILE_NOT_FOUND) -- path does not exist
        VeriFlowError(VF_INTERFACE_FILE_NO_PORTS)   -- no module declaration,
            or the (first) module declaration has zero ports
    Warns (UserWarning, not raised):
        file has 2+ module declarations -- the first (in file order) is used
        [VF_INTERFACE_FILE_MULTIPLE_MODULES]
    """
    path = Path(path)
    if not path.exists():
        raise VeriFlowError(
            f"Interface definition file not found: {path}",
            code="VF_INTERFACE_FILE_NOT_FOUND",
            details={"path": str(path)},
        )
    text = path.read_text(encoding="utf-8")

    modules = _find_module_names(text)
    if not modules:
        raise VeriFlowError(
            f"No module declaration found in {path}.",
            code="VF_INTERFACE_FILE_NO_PORTS",
            details={"path": str(path)},
        )
    if len(modules) > 1:
        warnings.warn(
            f"Multiple module declarations found in {path}: {', '.join(modules)}. "
            f"Using {modules[0]!r}. [VF_INTERFACE_FILE_MULTIPLE_MODULES]",
            stacklevel=2,
        )
    module_name = modules[0]

    raw_ports = extract_ports(text, module_name)
    if not raw_ports:
        raise VeriFlowError(
            f"Module {module_name!r} in {path} has no ports.",
            code="VF_INTERFACE_FILE_NO_PORTS",
            details={"path": str(path), "module": module_name},
        )
    ports = tuple(
        InterfacePort(
            name=name,
            direction=direction,
            width=width if width is not None else 1,
        )
        for name, direction, width in raw_ports
    )

    description = ""
    requires_top_module = False
    port_descriptions: dict[str, str] | None = None
    meta_path = path.parent / "meta.yaml"
    if meta_path.exists():
        meta = yaml.safe_load(meta_path.read_text(encoding="utf-8")) or {}
        description = meta.get("description") or ""
        requires_top_module = bool(meta.get("requires_top_module", False))
        raw_port_descriptions = meta.get("port_descriptions")
        if isinstance(raw_port_descriptions, dict) and raw_port_descriptions:
            port_descriptions = {
                str(k): str(v) for k, v in raw_port_descriptions.items()
            }

    tb_template_path = path.parent / "tb_template.v"
    tb_template = str(tb_template_path) if tb_template_path.exists() else None

    return InterfaceProfile(
        name=module_name,
        ports=ports,
        description=description,
        requires_top_module=requires_top_module,
        tb_template=tb_template,
        port_descriptions=port_descriptions,
    )


def _load_builtin_interfaces() -> dict[str, Callable[[], InterfaceProfile]]:
    """Scan INTERFACES_DIR for `<name>/interface.v` subdirectories and build
    one lazy factory per built-in interface, keyed by directory name.

    Returns an empty dict if INTERFACES_DIR doesn't exist (defensive -- e.g.
    a stripped-down install missing the data directory shouldn't crash at
    import time, just register zero built-in interfaces).
    """
    factories: dict[str, Callable[[], InterfaceProfile]] = {}
    if not INTERFACES_DIR.is_dir():
        return factories
    for subdir in sorted(p for p in INTERFACES_DIR.iterdir() if p.is_dir()):
        interface_file = subdir / "interface.v"
        if interface_file.exists():
            factories[subdir.name] = (lambda p=interface_file: load_interface_profile_from_file(p))
    return factories


# Built-in interface profile registry. Each entry maps a stable interface
# name to a factory returning a fresh (frozen) InterfaceProfile, so callers
# can never mutate registry state through a returned profile. Insertion
# order defines the deterministic ordering of the list functions.
_PROFILE_FACTORIES: dict[str, Callable[[], InterfaceProfile]] = _load_builtin_interfaces()


def semicolab_interface_profile() -> InterfaceProfile:
    """Backward-compatible accessor for the built-in "semicolab" profile.

    The 9-port contract itself now lives in
    `veriflow/interfaces/semicolab/interface.v` (loaded through the registry,
    same as any other interface) -- this wrapper exists only so existing call
    sites that import this function by name keep working unchanged.
    """
    return get_interface_profile("semicolab")


def list_interface_profile_names() -> list[str]:
    """Return the registered interface names in stable registration order."""
    return list(_PROFILE_FACTORIES)


def list_interface_profiles() -> list[InterfaceProfile]:
    """Return all registered InterfaceProfiles in stable registration order.

    A new list of freshly built profiles is returned on every call.
    """
    return [factory() for factory in _PROFILE_FACTORIES.values()]


def has_interface_profile(name: str) -> bool:
    """Return True if *name* is a registered interface profile."""
    return name in _PROFILE_FACTORIES


def default_interface_profile() -> InterfaceProfile | None:
    """Return the default InterfaceProfile, or None.

    VeriFlow has no default interface: projects must opt in explicitly via
    interface_name / interface.name, and an omitted or null value means a
    generic project with no interface checking.
    """
    return None


def get_interface_profile(name: str | None) -> InterfaceProfile | None:
    """Return the InterfaceProfile for *name*, or None for a generic project.

    Raises VF_INTERFACE_UNKNOWN for any non-empty name that is not registered.
    """
    if name is None:
        return None
    factory = _PROFILE_FACTORIES.get(name)
    if factory is not None:
        return factory()
    registered = ", ".join(_PROFILE_FACTORIES)
    raise VeriFlowError(
        f"Unknown interface name {name!r}. Registered interfaces: {registered}\n"
        "  Set interface_name to a registered value in project_config.yaml.",
        code="VF_INTERFACE_UNKNOWN",
        details={"interface_name": name},
    )


def register_interface_profile_from_file(path: Path) -> tuple[str, list[str]]:
    """Load an InterfaceProfile from an external `.v` file and register it.

    Used for project-supplied interfaces (`interface.definition:` in
    `veriflow.yaml` / `interface_definition:` in `project_config.yaml`) --
    unlike the built-in scan, the registered name comes from the parsed
    module name, not from any directory/file naming convention.

    Overwrites any existing profile registered under the same name --
    including a built-in one, so a project can locally redefine e.g.
    "semicolab" if it needs to.

    Returns (registered_name, config_warnings) -- registered_name is the
    parsed module name; config_warnings is a plain list of message
    strings (a "Overwriting existing interface profile..."
    [VF_INTERFACE_PROFILE_OVERWRITTEN] entry when applicable, otherwise
    empty). These are deliberately NOT emitted via `warnings.warn()`:
    unlike VF_INTERFACE_FILE_MULTIPLE_MODULES (raised by
    `load_interface_profile_from_file` above, which can also fire later
    from a stored profile factory, well outside any config-parsing call --
    a broader case left as a real Python warning), this one only ever
    fires exactly once, synchronously, from a config-parsing call site
    that can collect it and surface it properly: in `results.json`'s
    `warnings` array and via `print_warn()`'s clean CLI output, not a raw
    Python UserWarning traceback a user has to scroll past.
    """
    profile = load_interface_profile_from_file(Path(path))
    config_warnings: list[str] = []
    if profile.name in _PROFILE_FACTORIES:
        config_warnings.append(
            f"Overwriting existing interface profile {profile.name!r} with "
            f"external definition from {path}. [VF_INTERFACE_PROFILE_OVERWRITTEN]"
        )
    _PROFILE_FACTORIES[profile.name] = (lambda p=Path(path): load_interface_profile_from_file(p))
    return profile.name, config_warnings


# ── URL-sourced interface.definition ──────────────────────────────────────────

def _url_scheme(definition: str) -> str | None:
    """Return the lowercased scheme if *definition* looks like
    `<scheme>://...`, else None (a local path, relative or absolute --
    including Windows drive paths like `C:\\...`, which use a backslash,
    not `://`, so never match here)."""
    match = _URL_SCHEME_RE.match(definition)
    return match.group(1).lower() if match else None


def _cache_dir_for_url(url: str) -> Path:
    """VERIFLOW_INTERFACES_CACHE_ROOT/<sha256(url)> -- the URL itself is the
    cache key, so the same URL always resolves to the same directory
    regardless of which project/database referenced it."""
    return VERIFLOW_INTERFACES_CACHE_ROOT / hashlib.sha256(url.encode("utf-8")).hexdigest()


def _download_interface_url(url: str) -> Path:
    """Fetch *url* and (over)write its cache entry unconditionally --
    always hits the network. Returns the resulting interface.v path.

    Used both for a cache miss (`resolve_interface_definition`) and for an
    explicit `veriflow interface update <name>` (force re-fetch, ignoring
    whatever's already cached).

    Raises VeriFlowError(VF_INTERFACE_URL_FETCH_FAILED) for any network/HTTP
    error (connection failure, timeout, 404, etc.) -- urllib raises
    HTTPError (a URLError subclass) for non-2xx responses, so this single
    except clause covers both categories.
    """
    import urllib.error
    import urllib.request

    try:
        with urllib.request.urlopen(url, timeout=30) as response:
            content = response.read()
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise VeriFlowError(
            f"Failed to fetch interface definition from {url!r}: {exc}",
            code="VF_INTERFACE_URL_FETCH_FAILED",
            details={"url": url, "error": str(exc)},
        ) from exc

    cache_dir = _cache_dir_for_url(url)
    cache_dir.mkdir(parents=True, exist_ok=True)
    interface_path = cache_dir / "interface.v"
    interface_path.write_bytes(content)
    # Recorded alongside the .v so `veriflow interface update <name>` can
    # later re-resolve "this profile name" back to "the URL that produced
    # it" -- the cache directory itself is only named by URL hash, not by
    # the (not-yet-known-until-parsed) profile name.
    (cache_dir / "source_url.txt").write_text(url, encoding="utf-8")
    return interface_path


def resolve_interface_definition(definition: str, base_dir: Path) -> Path:
    """Resolve an `interface.definition:`/`interface_definition:` value to
    a local `.v` file path.

    *definition* is either:
    - an `http://`/`https://` URL: resolved through the permanent local
      cache (VERIFLOW_INTERFACES_CACHE_ROOT/<sha256(url)>/interface.v) --
      a cache hit returns immediately with no network access at all; a
      cache miss downloads once and caches permanently (see
      `_download_interface_url`). Never re-fetched implicitly after that --
      only an explicit `veriflow interface update <name>` does.
    - anything else: treated as a local path, resolved relative to
      *base_dir* exactly as before this feature (unchanged behavior).

    Any other URL scheme (`file://`, `ftp://`, etc.) is rejected outright --
    only http(s) is supported.

    Raises:
        VeriFlowError(VF_INTERFACE_URL_SCHEME_NOT_ALLOWED) -- a non-http(s) scheme
        VeriFlowError(VF_INTERFACE_URL_FETCH_FAILED)       -- network/HTTP error on a cache miss
    """
    scheme = _url_scheme(definition)
    if scheme is None:
        return (Path(base_dir) / definition).resolve()

    if scheme not in _ALLOWED_URL_SCHEMES:
        raise VeriFlowError(
            f"Unsupported interface.definition URL scheme {scheme + '://'!r} in "
            f"{definition!r}. Only http:// and https:// are allowed.",
            code="VF_INTERFACE_URL_SCHEME_NOT_ALLOWED",
            details={"definition": definition, "scheme": scheme},
        )

    interface_path = _cache_dir_for_url(definition) / "interface.v"
    if interface_path.is_file():
        return interface_path  # cache hit -- no network access

    return _download_interface_url(definition)


def find_cached_interface_by_name(name: str) -> tuple[Path, str] | None:
    """Scan VERIFLOW_INTERFACES_CACHE_ROOT for a cached interface.v whose
    declared module name matches *name*.

    Returns (cache_dir, source_url), or None if *name* was never downloaded
    from a URL at all (a built-in profile, a local-file `interface.definition`,
    or simply never referenced)."""
    if not VERIFLOW_INTERFACES_CACHE_ROOT.is_dir():
        return None
    for cache_dir in sorted(p for p in VERIFLOW_INTERFACES_CACHE_ROOT.iterdir() if p.is_dir()):
        interface_path = cache_dir / "interface.v"
        source_url_path = cache_dir / "source_url.txt"
        if not interface_path.is_file() or not source_url_path.is_file():
            continue
        text = interface_path.read_text(encoding="utf-8")
        if name in _find_module_names(text):
            return cache_dir, source_url_path.read_text(encoding="utf-8").strip()
    return None


def update_cached_interface_url(name: str) -> str:
    """Force re-download the URL-sourced interface profile registered as
    *name*, overwriting its cached interface.v. Returns the source URL that
    was re-fetched.

    Raises VeriFlowError(VF_INTERFACE_UPDATE_NOT_FOUND) if *name* has no
    cached URL-based definition -- either it was never downloaded from a
    URL, or it's a built-in/local-file-based profile with nothing to
    re-fetch in the first place.
    """
    found = find_cached_interface_by_name(name)
    if found is None:
        raise VeriFlowError(
            f"No cached URL-based interface definition found for {name!r}. "
            "Only interfaces originally loaded via "
            "interface.definition: http(s)://... (or interface_definition: "
            "in Database Mode) can be updated -- built-in interfaces and "
            "local-file definitions have nothing to re-fetch.",
            code="VF_INTERFACE_UPDATE_NOT_FOUND",
            details={"name": name},
        )
    _cache_dir, source_url = found
    _download_interface_url(source_url)
    return source_url


def list_cached_interface_urls() -> list[dict]:
    """Return every cached URL-based interface definition, sorted by name.

    Each entry: {"name": str, "url": str, "downloaded_at": datetime} --
    "downloaded_at" is interface.v's mtime (updated on every
    `veriflow interface update`, since that overwrites the file in place).
    "name" is parsed fresh from the cached file's current content, not
    stored separately, so it always reflects what's actually on disk right
    now (e.g. after a URL's content changed name across an update).
    """
    entries: list[dict] = []
    if VERIFLOW_INTERFACES_CACHE_ROOT.is_dir():
        for cache_dir in sorted(p for p in VERIFLOW_INTERFACES_CACHE_ROOT.iterdir() if p.is_dir()):
            interface_path = cache_dir / "interface.v"
            source_url_path = cache_dir / "source_url.txt"
            if not interface_path.is_file() or not source_url_path.is_file():
                continue
            modules = _find_module_names(interface_path.read_text(encoding="utf-8"))
            entries.append({
                "name": modules[0] if modules else "?",
                "url": source_url_path.read_text(encoding="utf-8").strip(),
                "downloaded_at": datetime.fromtimestamp(interface_path.stat().st_mtime),
            })
    entries.sort(key=lambda e: e["name"])
    return entries
