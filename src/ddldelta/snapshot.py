# Schema snapshots: persist the parsed model as JSON so a later run can
# diff against it without keeping old DDL deliveries around - the
# workflow's memory (bootstrap: no snapshot yet = initial state, every
# table is new). Versioned so a future format change can be rejected
# instead of silently misread.

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ddldelta.ddl_parser import ParseResult
from ddldelta.errors import GenerationError
from ddldelta.model import Column, Schema, Table
from ddldelta.sources import SchemaPair, parse_path

SNAPSHOT_VERSION = 1
_MARKER = "ddldelta_snapshot"


def schema_to_dict(schema: Schema, label: str) -> dict[str, Any]:
    """Schema -> the versioned JSON-able snapshot format."""
    return {
        _MARKER: SNAPSHOT_VERSION,
        "label": label,
        "tables": {
            name: {
                "columns": [
                    {"name": c.name, "type": c.type, "not_null": c.not_null}
                    for c in table.columns
                ],
                "key": list(table.key),
            }
            for name, table in schema.items()
        },
    }


def schema_from_dict(data: Mapping[str, Any]) -> tuple[str, dict[str, Table]]:
    """The inverse of schema_to_dict. Validates structure BEFORE any access
    - a scalar or otherwise foreign JSON document raises a clear
    GenerationError instead of a bare TypeError/KeyError. Raises
    GenerationError if: data is not a JSON object; the marker is missing or
    the version unknown; 'label' is not a string; 'tables' is not an
    object; or any table entry lacks a 'columns' list of {name, type,
    not_null} objects and a 'key' list."""
    if not isinstance(data, Mapping):
        raise GenerationError(
            f"not a ddldelta snapshot: expected a JSON object, got {type(data).__name__}")
    if _MARKER not in data:
        raise GenerationError(f"not a ddldelta snapshot: missing '{_MARKER}' marker")
    version = data[_MARKER]
    if version != SNAPSHOT_VERSION:
        raise GenerationError(f"unknown ddldelta snapshot version: {version!r}")
    if not isinstance(data.get("label"), str):
        raise GenerationError("ddldelta snapshot: 'label' must be a string")
    tables_data = data.get("tables")
    if not isinstance(tables_data, Mapping):
        raise GenerationError("ddldelta snapshot: 'tables' must be an object")
    tables: dict[str, Table] = {}
    for name, t in tables_data.items():
        if not isinstance(t, Mapping):
            raise GenerationError(f"ddldelta snapshot: table {name!r} must be an object")
        columns_data = t.get("columns")
        if not isinstance(columns_data, list):
            raise GenerationError(f"ddldelta snapshot: table {name!r} 'columns' must be a list")
        columns = []
        for c in columns_data:
            if (not isinstance(c, Mapping)
                    or not isinstance(c.get("name"), str)
                    or not isinstance(c.get("type"), str)
                    or not isinstance(c.get("not_null"), bool)):
                raise GenerationError(
                    f"ddldelta snapshot: table {name!r} has a malformed column "
                    "(expected name/type/not_null)")
            columns.append(Column(c["name"], c["type"], c["not_null"]))
        key = t.get("key")
        if not isinstance(key, list) or not all(isinstance(k, str) for k in key):
            raise GenerationError(
                f"ddldelta snapshot: table {name!r} 'key' must be a list of strings")
        tables[name] = Table(name, tuple(columns), tuple(key))
    return data["label"], tables


def save_snapshot(path: Path, schema: Schema, label: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(schema_to_dict(schema, label), indent=2) + "\n",
                    encoding="utf-8")


def load_snapshot(path: Path) -> tuple[str, dict[str, Table]]:
    """GenerationError naming path on a missing file, invalid JSON, or a
    missing/unknown snapshot marker."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as error:
        raise GenerationError(f"snapshot {path}: {error}") from None
    try:
        data = json.loads(text)
    except json.JSONDecodeError as error:
        raise GenerationError(f"snapshot {path}: invalid JSON ({error})") from None
    try:
        return schema_from_dict(data)
    except GenerationError as error:
        raise GenerationError(f"snapshot {path}: {error}") from None


@dataclass(frozen=True)
class SnapshotSource:
    """PairSource: old state from a snapshot file, new state from a DDL
    path (directory or single .sql file). A missing snapshot file means
    initial state by default (bootstrap: first run has nothing to diff
    against) - but that same silence is a footgun in an unattended
    pipeline: a typo'd snapshot path means every table looks brand new,
    the run "succeeds", regenerates a full CREATE set under a new label,
    and the mistake only surfaces later at deploy time as a confusing
    "object already exists" from schemachange/Flyway, far from its cause.
    Set require_snapshot=True to fail fast instead - a missing file then
    raises GenerationError naming the path, right where the typo was made."""
    snapshot: Path
    new: Path
    parse_ddl: Callable[[str], ParseResult]
    new_label: str | None = None
    require_snapshot: bool = False

    def load(self) -> SchemaPair:
        old_label: str | None
        old: dict[str, Table]
        if self.snapshot.exists():
            old_label, old = load_snapshot(self.snapshot)
        elif self.require_snapshot:
            raise GenerationError(
                f"snapshot {self.snapshot} does not exist and require_snapshot=True")
        else:
            old_label, old = None, {}
        return SchemaPair(old_label, self.new_label or self.new.name,
                          old, parse_path(self.parse_ddl, self.new))
