"""Comment-preserving YAML config editor for `project set` / `db set` /
`db tile set`.

Uses ruamel.yaml's round-trip mode when available -- updating an existing
key keeps its position and attached comments (a `CommentedMap`, unlike
`dict`, remembers both); a brand-new key (including one that only exists
as a *commented-out* example in a scaffold, since comments aren't parsed
as data) is appended at the end, leaving the original commented example
untouched above it as documentation. Falls back to a line-based text
patch when ruamel.yaml isn't installed (it's an optional dependency --
see setup.py's `yaml-edit` extra).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

try:
    from ruamel.yaml import YAML
    from ruamel.yaml.comments import CommentedMap
    from ruamel.yaml.scalarstring import DoubleQuotedScalarString, LiteralScalarString

    HAS_RUAMEL = True
except ImportError:  # pragma: no cover -- exercised in environments without ruamel.yaml
    HAS_RUAMEL = False


def _make_yaml() -> "YAML":
    yaml = YAML()
    yaml.preserve_quotes = True
    yaml.indent(mapping=2, sequence=4, offset=2)
    yaml.width = 4096  # avoid re-wrapping long values across lines
    return yaml


def set_yaml_key(
    path: Path, key_path: tuple[str, ...], value: Any, *, block_scalar: bool = False, quoted: bool = False
) -> None:
    """Set the (possibly one-level-nested) key given by *key_path* to
    *value* in the YAML file at *path*, preserving comments/formatting.

    *key_path* is 1 element for a flat top-level key (e.g. ``("id_prefix",)``
    or ``("interface",)`` when clearing it to null) or 2 elements for a
    nested ``parent: {child: value}`` key (e.g. ``("interface", "name")``).

    *block_scalar*: dump a string *value* as a literal ``|`` block scalar
    (matches tile_config.yaml's multi-line fields like ``description:``)
    instead of a quoted/plain flow scalar.

    *quoted*: force a string *value* to render double-quoted. Updating a
    key that's *already* double-quoted in the file (e.g. tile_config.yaml's
    ``tile_name: ""``) retains that quoting automatically via ruamel's
    round-trip mode without needing this -- it's only needed for a value
    being written into a key that doesn't have an existing quoted example
    to inherit the style from (e.g. project_config.yaml's ``shuttle_name``/
    ``id_format``, commented out by default so ruamel sees them as brand
    new keys, not updates to an existing quoted one).
    """
    if HAS_RUAMEL:
        _set_yaml_key_ruamel(path, key_path, value, block_scalar=block_scalar, quoted=quoted)
    else:
        _set_yaml_key_fallback(path, key_path, value, block_scalar=block_scalar)


def set_yaml_pipeline(path: Path, stages: list[dict]) -> None:
    """Set the top-level ``pipeline: {stages: [...]}`` section to *stages*
    (a list of ``{"type": ..., ["backend": ...]}`` dicts), preserving
    comments/formatting the same way as `set_yaml_key`."""
    if HAS_RUAMEL:
        _set_yaml_pipeline_ruamel(path, stages)
    else:
        _set_yaml_pipeline_fallback(path, stages)


# ── ruamel.yaml round-trip implementation ──────────────────────────────────

def _load_ruamel(path: Path, yaml: "YAML"):
    with path.open("r", encoding="utf-8") as f:
        data = yaml.load(f)
    if data is None:
        data = CommentedMap()
    return data


def _dump_ruamel(data, path: Path, yaml: "YAML") -> None:
    with path.open("w", encoding="utf-8") as f:
        yaml.dump(data, f)


def _set_yaml_key_ruamel(
    path: Path, key_path: tuple[str, ...], value: Any, *, block_scalar: bool, quoted: bool = False
) -> None:
    yaml = _make_yaml()
    data = _load_ruamel(path, yaml)

    if block_scalar and isinstance(value, str):
        text = value if value.endswith("\n") else value + "\n"
        value = LiteralScalarString(text)
    elif quoted and isinstance(value, str):
        value = DoubleQuotedScalarString(value)

    node = data
    for key in key_path[:-1]:
        existing = node.get(key)
        if not isinstance(existing, dict):
            existing = CommentedMap()
            node[key] = existing
        node = existing
    node[key_path[-1]] = value

    _dump_ruamel(data, path, yaml)


def _set_yaml_pipeline_ruamel(path: Path, stages: list[dict]) -> None:
    yaml = _make_yaml()
    data = _load_ruamel(path, yaml)

    pipeline_section = data.get("pipeline")
    if not isinstance(pipeline_section, dict):
        pipeline_section = CommentedMap()
        data["pipeline"] = pipeline_section
    pipeline_section["stages"] = [dict(stage) for stage in stages]

    _dump_ruamel(data, path, yaml)


# ── text-patch fallback (no ruamel.yaml installed) ─────────────────────────

def _render_scalar(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    escaped = str(value).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _section_end(lines: list[str], start: int) -> int:
    """Return the index just past the indented block following lines[start]
    (a parent `key:` line) -- the first line that is blank or itself
    indented is part of the section; the first dedented, non-blank line
    (or end of file) ends it."""
    end = start + 1
    while end < len(lines):
        line = lines[end]
        if line.strip() == "" or re.match(r"^\s+\S", line):
            end += 1
            continue
        break
    return end


def _set_yaml_key_fallback(path: Path, key_path: tuple[str, ...], value: Any, *, block_scalar: bool) -> None:
    text = path.read_text(encoding="utf-8")
    if block_scalar and isinstance(value, str):
        text = _fallback_set_block_scalar(text, key_path[-1], value)
    elif len(key_path) == 1:
        text = _fallback_set_top_level(text, key_path[0], value)
    else:
        text = _fallback_set_nested(text, key_path[0], key_path[1], value)
    path.write_text(text, encoding="utf-8")


def _fallback_set_top_level(text: str, key: str, value: Any) -> str:
    rendered = _render_scalar(value)
    pattern = re.compile(rf"^{re.escape(key)}:.*$", re.MULTILINE)
    new_line = f"{key}: {rendered}"
    if pattern.search(text):
        return pattern.sub(new_line, text, count=1)
    sep = "" if (not text or text.endswith("\n")) else "\n"
    return f"{text}{sep}{new_line}\n"


def _fallback_set_nested(text: str, parent_key: str, child_key: str, value: Any) -> str:
    rendered = _render_scalar(value)
    lines = text.splitlines(keepends=True)
    parent_re = re.compile(rf"^{re.escape(parent_key)}:\s*(#.*)?$")
    child_re = re.compile(rf"^\s+{re.escape(child_key)}:.*$")

    parent_idx = next((i for i, line in enumerate(lines) if parent_re.match(line)), None)

    if parent_idx is None:
        sep = "" if (not lines or lines[-1].endswith("\n")) else "\n"
        addition = f"{sep}{parent_key}:\n  {child_key}: {rendered}\n"
        return "".join(lines) + addition

    end = _section_end(lines, parent_idx)
    child_idx = next(
        (i for i in range(parent_idx + 1, end) if child_re.match(lines[i])), None
    )
    if child_idx is not None:
        lines[child_idx] = f"  {child_key}: {rendered}\n"
    else:
        lines.insert(parent_idx + 1, f"  {child_key}: {rendered}\n")

    return "".join(lines)


def _fallback_set_block_scalar(text: str, key: str, value: str) -> str:
    lines = text.splitlines(keepends=True)
    key_re = re.compile(rf"^{re.escape(key)}:\s*\|?\s*$")
    key_idx = next((i for i, line in enumerate(lines) if key_re.match(line)), None)
    new_content = [f"  {ln}\n" for ln in value.splitlines()] or ["  \n"]

    if key_idx is None:
        sep = "" if (not lines or lines[-1].endswith("\n")) else "\n"
        return "".join(lines) + sep + f"{key}: |\n" + "".join(new_content)

    end = _section_end(lines, key_idx)
    return "".join(lines[:key_idx]) + f"{key}: |\n" + "".join(new_content) + "".join(lines[end:])


def _render_pipeline_block(stages: list[dict]) -> str:
    out = ["pipeline:", "  stages:"]
    for stage in stages:
        out.append(f"    - type: {stage['type']}")
        if stage.get("backend"):
            out.append(f"      backend: {stage['backend']}")
    return "\n".join(out) + "\n"


def _set_yaml_pipeline_fallback(path: Path, stages: list[dict]) -> None:
    text = path.read_text(encoding="utf-8")
    block = _render_pipeline_block(stages)
    lines = text.splitlines(keepends=True)
    parent_re = re.compile(r"^pipeline:\s*(#.*)?$")
    parent_idx = next((i for i, line in enumerate(lines) if parent_re.match(line)), None)

    if parent_idx is None:
        sep = "" if (not lines or lines[-1].endswith("\n")) else "\n"
        new_text = "".join(lines) + sep + block
    else:
        end = _section_end(lines, parent_idx)
        new_text = "".join(lines[:parent_idx]) + block + "".join(lines[end:])

    path.write_text(new_text, encoding="utf-8")
