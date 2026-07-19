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


def _represent_none_as_null(representer, data):
    """ruamel's default null representer writes an empty scalar (`key:`
    with nothing after it) -- render the explicit `null` literal instead,
    so e.g. `project set interface null` produces `interface: null`, not
    a value-less `interface:`. Both parse back to Python None identically,
    this only affects what's written to disk."""
    return representer.represent_scalar("tag:yaml.org,2002:null", "null")


def _make_yaml() -> "YAML":
    yaml = YAML()
    yaml.preserve_quotes = True
    yaml.indent(mapping=2, sequence=4, offset=2)
    yaml.width = 4096  # avoid re-wrapping long values across lines
    yaml.representer.add_representer(type(None), _represent_none_as_null)
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

    If *key_path* exists only as a commented-out placeholder (e.g.
    ``# interface:\\n#   name: ""``, the scaffolded default), it's
    uncommented and updated in place instead of appending a second, active
    copy of the section at the end of the file -- this is a pure text
    operation that runs the same way whether or not ruamel.yaml is
    installed. Only when no commented match exists do we fall through to
    the ruamel/fallback update-or-append behavior below.
    """
    text = path.read_text(encoding="utf-8")
    uncommented = _uncomment_existing_section(
        text, key_path, value, block_scalar=block_scalar, quoted=quoted
    )
    if uncommented is not None:
        path.write_text(uncommented, encoding="utf-8")
        return

    if HAS_RUAMEL:
        _set_yaml_key_ruamel(path, key_path, value, block_scalar=block_scalar, quoted=quoted)
    else:
        _set_yaml_key_fallback(path, key_path, value, block_scalar=block_scalar)


# ── commented-placeholder uncommenting (shared by both implementations) ────

def _render_uncommented_value(value: Any, *, quoted: bool) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    text = str(value)
    if quoted:
        escaped = text.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    return text


def _commented_block_end(lines: list[str], start: int) -> int:
    """Return the index just past the run of commented lines following
    lines[start] (a `# key:` comment line) -- ends at the first blank line
    or the first line that isn't itself a comment (mirrors _section_end's
    role for the active-YAML case, but for a still-commented-out block)."""
    end = start + 1
    while end < len(lines):
        line = lines[end]
        if line.strip() == "" or not line.lstrip().startswith("#"):
            break
        end += 1
    return end


def _find_commented_line(lines: list[str], start: int, end: int, key: str) -> int | None:
    pattern = re.compile(rf"^#\s*{re.escape(key)}:")
    return next((i for i in range(start, end) if pattern.match(lines[i])), None)


def _find_active_line(lines: list[str], key: str) -> int | None:
    """Index of *key* as an already-active (uncommented, column-0-anchored)
    top-level line, or None. Anchoring at column 0 with no leading `#`
    naturally excludes both commented lines and nested child lines (which
    are indented) -- this only ever matches a real top-level `key:`."""
    pattern = re.compile(rf"^{re.escape(key)}:")
    return next((i for i, line in enumerate(lines) if pattern.match(line)), None)


def _uncomment_existing_section(
    text: str, key_path: tuple[str, ...], value: Any, *, block_scalar: bool, quoted: bool
) -> str | None:
    """If *key_path* exists only as a commented-out placeholder in *text*,
    uncomment and update it in place, returning the new full text.
    Returns None -- the caller then falls through to updating an existing
    *active* key in place or appending a brand new section at the end
    (unchanged pre-existing behavior) -- when either:

    - *key_path*'s top-level key is already active somewhere in the file
      (even if a stale commented placeholder for it also still exists
      elsewhere): uncommenting the placeholder here would create a
      *second*, duplicate top-level section instead of updating the one
      real section that's already there. The existing update-in-place
      logic (ruamel's key lookup / the fallback's active-line regex)
      already finds and updates that real section correctly on its own.
    - no commented match exists either.
    """
    if block_scalar and isinstance(value, str):
        # No template ships a block-scalar field (e.g. tile_config.yaml's
        # description:) as a commented-out placeholder -- they're all
        # already active -- so there is never anything to uncomment here.
        return None

    lines = text.splitlines(keepends=True)
    rendered = _render_uncommented_value(value, quoted=quoted)
    top_level_key = key_path[0]

    if _find_active_line(lines, top_level_key) is not None:
        return None

    if len(key_path) == 1:
        idx = _find_commented_line(lines, 0, len(lines), top_level_key)
        if idx is None:
            return None
        lines[idx] = f"{top_level_key}: {rendered}\n"
        return "".join(lines)

    parent_key, child_key = key_path
    parent_idx = _find_commented_line(lines, 0, len(lines), parent_key)
    if parent_idx is None:
        return None

    block_end = _commented_block_end(lines, parent_idx)
    child_idx = _find_commented_line(lines, parent_idx + 1, block_end, child_key)

    lines[parent_idx] = f"{parent_key}:\n"
    if child_idx is not None:
        lines[child_idx] = f"  {child_key}: {rendered}\n"
    else:
        lines.insert(parent_idx + 1, f"  {child_key}: {rendered}\n")

    return "".join(lines)


def set_yaml_pipeline(path: Path, stages: list[dict]) -> None:
    """Set the top-level ``pipeline: {stages: [...]}`` section to *stages*
    (a list of ``{"type": ..., ["backend": ...]}`` dicts), preserving
    comments/formatting the same way as `set_yaml_key`."""
    if HAS_RUAMEL:
        _set_yaml_pipeline_ruamel(path, stages)
    else:
        _set_yaml_pipeline_fallback(path, stages)


def set_yaml_nested_keys(path: Path, parent_key: str, children: dict[str, Any]) -> None:
    """Set multiple one-level-nested children of *parent_key* (e.g.
    ``interface: {name: ..., definition: ...}``) in a single pass.

    Setting them one at a time via separate `set_yaml_key()` calls is
    unsafe here: adding a *second* key to a mapping whose only existing
    key has a large trailing comment attached (as happens right after the
    first key was just uncommented from a scaffold placeholder -- every
    remaining commented-out section in the file can end up bundled onto
    that one key's comment slot, see `_uncomment_existing_section`'s
    docstring) can push the second key's value to the very end of the
    file in ruamel's dump, landing outside the mapping it was meant to be
    part of. Setting every child in the same read-modify-write pass never
    creates that fragile one-key intermediate state.

    Order of *children*'s keys is preserved when uncommenting a
    placeholder (each is looked up as its own `#   child:` line within the
    parent's commented block, same as `set_yaml_key`); when the parent
    already has other children (active or being added fresh), order
    follows however the underlying dict/YAML naturally lays them out.
    """
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)

    if _find_active_line(lines, parent_key) is None:
        parent_idx = _find_commented_line(lines, 0, len(lines), parent_key)
        if parent_idx is not None:
            block_end = _commented_block_end(lines, parent_idx)
            lines[parent_idx] = f"{parent_key}:\n"
            insert_at = parent_idx + 1
            for child_key, value in children.items():
                rendered = _render_uncommented_value(value, quoted=False)
                child_idx = _find_commented_line(lines, parent_idx + 1, block_end, child_key)
                if child_idx is not None:
                    lines[child_idx] = f"  {child_key}: {rendered}\n"
                    insert_at = child_idx + 1
                else:
                    lines.insert(insert_at, f"  {child_key}: {rendered}\n")
                    insert_at += 1
                    block_end += 1
            path.write_text("".join(lines), encoding="utf-8")
            return

    if HAS_RUAMEL:
        yaml = _make_yaml()
        data = _load_ruamel(path, yaml)
        node = data.get(parent_key)
        if not isinstance(node, dict):
            node = CommentedMap()
            data[parent_key] = node
        for child_key, value in children.items():
            node[child_key] = value
        _dump_ruamel(data, path, yaml)
    else:
        # The fallback's insert-new-child branch (_fallback_set_nested)
        # always inserts immediately after the parent's own key line,
        # regardless of any trailing comments further down -- it doesn't
        # share ruamel's comment-bundling hazard, so sequential calls here
        # are safe.
        for child_key, value in children.items():
            current = path.read_text(encoding="utf-8")
            path.write_text(_fallback_set_nested(current, parent_key, child_key, value), encoding="utf-8")


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

    old_value = node.get(key_path[-1])
    if (
        isinstance(value, list)
        and not _is_block_style(old_value)
        and hasattr(node, "ca")
        and key_path[-1] in node.ca.items
    ):
        # Replacing a scalar/flow value (e.g. `rtl_sources: []  # comment`,
        # or a hand-written `rtl_sources: [a.v, b.v]  # comment`) with a
        # multi-line block sequence while keeping that value's attached
        # end-of-line comment confuses ruamel's comment-anchoring: the
        # comment stays put but the new list's items get dumped several
        # lines further down (after the next few keys/comments), landing
        # nowhere near the key they belong to -- confusing on its own, and
        # actively corrupting if a *later* edit inserts any new active
        # top-level key ahead of that stranded position (e.g. uncommenting
        # `# interface:`): that new key terminates the mapping's
        # value-scanning before the parser ever reaches the orphaned
        # sequence, producing invalid YAML
        # (`ParserError: expected <block end>, but found
        # '<block sequence start>'`) that only surfaces on the *next* read,
        # not at the `set` call that caused it (see
        # dev-docs/SMOKE_TEST_FINDINGS.md, 2026-07-19).
        #
        # Dropping the comment when shifting shape from flow/scalar to
        # block avoids that -- a stale inline hint next to a field the user
        # just populated for real has served its purpose anyway.
        #
        # `_is_block_style` (not a bare `isinstance(old_value, list)`) is
        # what decides whether this transition needs guarding: an empty
        # flow list (`rtl_sources: []`, the scaffold default) is *already*
        # `isinstance(..., list)` == True, so a plain list check never
        # fires here for the single most common case -- the very first
        # `project set rtl-sources`/`tb-sources` call against a fresh
        # scaffold. Only an *existing block* list being replaced by a new
        # one (the common case after the *second* `project set
        # rtl-sources`) is genuinely unaffected and already round-trips its
        # surrounding comments correctly on its own -- that's the one case
        # this guard must NOT fire for, to avoid dropping a comment that
        # doesn't need dropping.
        del node.ca.items[key_path[-1]]

    node[key_path[-1]] = value

    _dump_ruamel(data, path, yaml)


def _is_block_style(value: Any) -> bool:
    """True only when *value* is an existing ruamel block-style sequence
    (multi-line `- item`) or mapping -- the one shape whose comments
    already round-trip safely on their own (see the guard above).

    Everything else needs the guard's protection:
      - A plain Python scalar or `None` (no `.fa` attribute at all) -- the
        original scalar-to-list transition the guard was written for.
      - An *empty* flow collection (`rtl_sources: []`): ruamel has nothing
        to record a style for, so `fa.flow_style()` is `None`, not `False`
        -- this is the exact case the pre-fix `isinstance(old_value, list)`
        check let slip through, since `[]` already satisfies `isinstance`.
      - An explicit non-empty flow collection (`rtl_sources: [a, b]`):
        `fa.flow_style()` is `True`.

    Only a real ruamel `.fa.flow_style() is False` -- set exclusively by
    the block-sequence/mapping parser -- means "already block style,
    nothing to fix."
    """
    fa = getattr(value, "fa", None)
    if fa is None:
        return False
    return fa.flow_style() is False


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


def _indent_of(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _value_extent_end(lines: list[str], key_idx: int) -> int:
    """Return the index just past the *value* of the key at lines[key_idx]:
    every subsequent line indented strictly more than the key line itself
    (blank lines pass through without ending the value) -- covers a
    block scalar's content lines, an existing list's `- item` lines, or a
    multi-line inline comment continuing the key's own line. Stops at the
    first non-blank line at or below the key's own indentation (a sibling
    key, a dedented comment block, or EOF) -- unlike `_section_end`, which
    treats *any* indentation as "still part of this section" and would
    incorrectly swallow a sibling key at the same indent as lines[key_idx]
    (e.g. another key nested one level deeper than a shared parent)."""
    key_indent = _indent_of(lines[key_idx])
    end = key_idx + 1
    while end < len(lines):
        line = lines[end]
        if line.strip() == "":
            end += 1
            continue
        if _indent_of(line) > key_indent:
            end += 1
            continue
        break
    return end


def _render_fallback_value_lines(key: str, value: Any, *, indent: str) -> list[str]:
    """Render `{indent}{key}: value` (scalar) or `{indent}{key}:` followed
    by `{indent}  - item` lines (list) -- the fallback's only two value
    shapes. `indent` is however many spaces the key itself sits at (`""`
    for a top-level key, `"  "` for a one-level-nested child)."""
    if isinstance(value, list):
        return [f"{indent}{key}:\n"] + [f"{indent}  - {item}\n" for item in value]
    return [f"{indent}{key}: {_render_scalar(value)}\n"]


def _set_yaml_key_fallback(path: Path, key_path: tuple[str, ...], value: Any, *, block_scalar: bool) -> None:
    text = path.read_text(encoding="utf-8")
    if block_scalar and isinstance(value, str):
        if len(key_path) == 1:
            text = _fallback_set_block_scalar(text, key_path[0], value)
        else:
            text = _fallback_set_nested_block_scalar(text, key_path[0], key_path[1], value)
    elif len(key_path) == 1:
        text = _fallback_set_top_level(text, key_path[0], value)
    else:
        text = _fallback_set_nested(text, key_path[0], key_path[1], value)
    path.write_text(text, encoding="utf-8")


def _fallback_set_top_level(text: str, key: str, value: Any) -> str:
    lines = text.splitlines(keepends=True)
    pattern = re.compile(rf"^{re.escape(key)}:")
    idx = next((i for i, line in enumerate(lines) if pattern.match(line)), None)
    new_lines = _render_fallback_value_lines(key, value, indent="")

    if idx is not None:
        # _value_extent_end (not the old bare single-line replace) also
        # removes any indented lines the old value owned -- e.g. a nested
        # mapping's children when clearing a section key to a plain scalar
        # (`interface: null` after `interface:\n  name: semicolab`), which
        # the single-line replace used to leave behind as an orphaned,
        # wrongly-indented continuation that ScannerError'd on reload.
        end = _value_extent_end(lines, idx)
        return "".join(lines[:idx]) + "".join(new_lines) + "".join(lines[end:])

    sep = "" if (not lines or lines[-1].endswith("\n")) else "\n"
    return "".join(lines) + sep + "".join(new_lines)


def _fallback_set_nested(text: str, parent_key: str, child_key: str, value: Any) -> str:
    lines = text.splitlines(keepends=True)
    parent_re = re.compile(rf"^{re.escape(parent_key)}:\s*(#.*)?$")
    child_re = re.compile(rf"^\s+{re.escape(child_key)}:.*$")
    new_lines = _render_fallback_value_lines(child_key, value, indent="  ")

    parent_idx = next((i for i, line in enumerate(lines) if parent_re.match(line)), None)

    if parent_idx is None:
        sep = "" if (not lines or lines[-1].endswith("\n")) else "\n"
        addition = f"{sep}{parent_key}:\n" + "".join(new_lines)
        return "".join(lines) + addition

    end = _section_end(lines, parent_idx)
    child_idx = next(
        (i for i in range(parent_idx + 1, end) if child_re.match(lines[i])), None
    )
    if child_idx is not None:
        # As in _fallback_set_top_level: consume whatever the existing
        # child value owned (e.g. an existing list's own `- item` lines),
        # not just its own key line.
        child_end = _value_extent_end(lines, child_idx)
        return "".join(lines[:child_idx]) + "".join(new_lines) + "".join(lines[child_end:])
    else:
        return "".join(lines[:parent_idx + 1]) + "".join(new_lines) + "".join(lines[parent_idx + 1:])


def _fallback_set_block_scalar(text: str, key: str, value: str) -> str:
    lines = text.splitlines(keepends=True)
    key_re = re.compile(rf"^{re.escape(key)}:\s*\|?\s*$")
    key_idx = next((i for i, line in enumerate(lines) if key_re.match(line)), None)
    new_content = [f"  {ln}\n" for ln in value.splitlines()] or ["  \n"]

    if key_idx is None:
        sep = "" if (not lines or lines[-1].endswith("\n")) else "\n"
        return "".join(lines) + sep + f"{key}: |\n" + "".join(new_content)

    end = _value_extent_end(lines, key_idx)
    return "".join(lines[:key_idx]) + f"{key}: |\n" + "".join(new_content) + "".join(lines[end:])


def _fallback_set_nested_block_scalar(text: str, parent_key: str, child_key: str, value: str) -> str:
    """Like _fallback_set_block_scalar, but for a one-level-nested block
    scalar (e.g. veriflow.yaml's `metadata.description`) -- the plain
    version ignores the parent entirely (searches for child_key as a
    *top-level* key), so a nested block scalar either collided with an
    unrelated top-level key of the same name or, more commonly since no
    such key exists, got appended as a stray top-level section instead of
    living under its actual parent."""
    lines = text.splitlines(keepends=True)
    parent_re = re.compile(rf"^{re.escape(parent_key)}:\s*(#.*)?$")
    child_re = re.compile(rf"^\s+{re.escape(child_key)}:\s*\|?\s*$")
    new_content = [f"    {ln}\n" for ln in value.splitlines()] or ["    \n"]
    new_lines = [f"  {child_key}: |\n"] + new_content

    parent_idx = next((i for i, line in enumerate(lines) if parent_re.match(line)), None)
    if parent_idx is None:
        sep = "" if (not lines or lines[-1].endswith("\n")) else "\n"
        return "".join(lines) + sep + f"{parent_key}:\n" + "".join(new_lines)

    end = _section_end(lines, parent_idx)
    child_idx = next(
        (i for i in range(parent_idx + 1, end) if child_re.match(lines[i])), None
    )
    if child_idx is not None:
        child_end = _value_extent_end(lines, child_idx)
        return "".join(lines[:child_idx]) + "".join(new_lines) + "".join(lines[child_end:])
    else:
        return "".join(lines[:parent_idx + 1]) + "".join(new_lines) + "".join(lines[parent_idx + 1:])


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
