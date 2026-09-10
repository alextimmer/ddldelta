# Things that produce a pair of schema states to compare. Today: delivery
# directories (n vs n-1, newest = lexicographic maximum) and an explicit
# two-state pair of paths. Later sources (schema snapshots, live
# introspection) implement the same Protocol.

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from itertools import groupby
from pathlib import Path
from typing import Protocol

from ddldelta.ddl_parser import ParseResult
from ddldelta.errors import GenerationError
from ddldelta.model import Column, Schema, Table, table_from


@dataclass(frozen=True)
class SchemaPair:
    old_label: str | None      # None: initial state, old is empty
    new_label: str
    old: Schema
    new: Schema

    @property
    def comparison(self) -> str:
        return f"{self.old_label or '(initial)'} -> {self.new_label}"


class PairSource(Protocol):
    def load(self) -> SchemaPair | None: ...


def _parse_file(parse_ddl: Callable[[str], ParseResult], path: Path) -> Table:
    try:
        name, columns, key = parse_ddl(path.read_text(encoding="utf-8"))
    except ValueError as error:
        raise GenerationError(f"DDL {path}: {error}") from None
    return table_from(name, columns, key)


def parse_ddl_dir(parse_ddl: Callable[[str], ParseResult], delivery_dir: Path) -> dict[str, Table]:
    """{table: Table} for every *.sql in the dir; a file without a
    parseable CREATE TABLE raises naming the file."""
    tables = {}
    for path in sorted(delivery_dir.glob("*.sql")):
        table = _parse_file(parse_ddl, path)
        tables[table.name] = table
    return tables


def parse_path(parse_ddl: Callable[[str], ParseResult], path: Path) -> dict[str, Table]:
    """A schema state from a directory (all *.sql files) or one .sql file.
    Raises GenerationError if path exists as neither."""
    if path.is_dir():
        return parse_ddl_dir(parse_ddl, path)
    if path.is_file():
        table = _parse_file(parse_ddl, path)
        return {table.name: table}
    raise GenerationError(f"schema state path {path} does not exist")


@dataclass(frozen=True)
class DeliveryDirectorySource:
    root: Path                                  # <ddl_dir>/<supplier>
    parse_ddl: Callable[[str], ParseResult]      # from ddl_parser.parser_for

    def load(self) -> SchemaPair | None:
        if not self.root.is_dir():
            raise GenerationError(f"delivery root {self.root} does not exist")
        deliveries = sorted(p for p in self.root.iterdir() if p.is_dir())
        if not deliveries:
            return None
        current = deliveries[-1]
        previous = deliveries[-2] if len(deliveries) > 1 else None
        return SchemaPair(
            previous.name if previous else None,
            current.name,
            parse_ddl_dir(self.parse_ddl, previous) if previous else {},
            parse_ddl_dir(self.parse_ddl, current))


@dataclass(frozen=True)
class PathPairSource:
    """Explicit two-state source: no naming convention - the caller says
    which state is old and which is new. Each path may be a directory of
    *.sql files or a single .sql file (one table). old=None means initial
    state (every table is new). Labels default to the path names and feed
    only the comparison string - version labels for renderers stay the
    caller's choice (build_plan's label argument).

    Note: two single files describing DIFFERENT tables diff as drop+create
    (critical) - a full-state comparison, not a rename detection.
    """
    old: Path | None
    new: Path
    parse_ddl: Callable[[str], ParseResult]
    old_label: str | None = None
    new_label: str | None = None

    def load(self) -> SchemaPair:
        return SchemaPair(
            self.old_label or (self.old.name if self.old else None),
            self.new_label or self.new.name,
            parse_path(self.parse_ddl, self.old) if self.old else {},
            parse_path(self.parse_ddl, self.new))


def rows_to_schema(rows: Iterable[tuple[str, str, str, bool]]) -> dict[str, Table]:
    """Schema from (table, column, type, not_null) rows, e.g. an
    information_schema query the CALLER ran (this package never connects
    to a database). Rows must be pre-ordered: grouped by table, columns in
    ordinal order - enforced: a table name that reappears in a later,
    non-consecutive group (interleaved rows) raises GenerationError instead
    of silently discarding the first group's columns. CAUTION for drift
    checks: the live catalog's type spellings (e.g. Snowflake's TEXT /
    NUMBER(38,0)) usually differ from the TypeMapping's output (VARCHAR /
    INT) - normalize types on the caller side before comparing, or diffs
    will report false type changes.
    """
    schema: dict[str, Table] = {}
    for name, group in groupby(rows, key=lambda row: row[0]):
        if name in schema:
            raise GenerationError(
                f"rows for table {name!r} are not consecutive - order rows by table, ordinal")
        schema[name] = Table(name, tuple(Column(column, type_, not_null)
                                         for _, column, type_, not_null in group))
    return schema
