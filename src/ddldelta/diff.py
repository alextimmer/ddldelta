# Pure structural comparison of two schema states into TYPED changes.
# No criticality, no SQL - that is policy.py / render.sql's job. Statement
# order is part of the byte contract of generated migrations: drops in old
# column order first, then per new column (DDL order) type before
# nullability before add.

from dataclasses import dataclass
from typing import cast

from ddldelta.model import Column, Schema, Table


@dataclass(frozen=True)
class CreateTable:
    table: Table


@dataclass(frozen=True)
class DropTable:
    name: str


@dataclass(frozen=True)
class AddColumn:
    table: str
    column: Column


@dataclass(frozen=True)
class DropColumn:
    table: str
    column: str


@dataclass(frozen=True)
class TypeChange:
    table: str
    column: str
    old_type: str
    new_type: str


@dataclass(frozen=True)
class NullabilityChange:
    table: str
    column: str
    not_null: bool          # the NEW state


type Change = (CreateTable | DropTable | AddColumn | DropColumn
               | TypeChange | NullabilityChange)


def table_diff(old: Table | None, new: Table | None) -> tuple[Change, ...]:
    """Changes turning old into new; either side may be None (absent)."""
    if old is None and new is None:
        return ()
    if old is None:
        return (CreateTable(cast(Table, new)),)
    if new is None:
        return (DropTable(old.name),)
    olds, news = old.columns_by_name, new.columns_by_name
    changes: list[Change] = []
    for name in olds:
        if name not in news:
            changes.append(DropColumn(new.name, name))
    for name, column in news.items():
        if name not in olds:
            changes.append(AddColumn(new.name, column))
            continue
        before = olds[name]
        if before.type != column.type:
            changes.append(TypeChange(new.name, name, before.type, column.type))
        if before.not_null != column.not_null:
            changes.append(NullabilityChange(new.name, name, column.not_null))
    return tuple(changes)


def schema_diff(old: Schema, new: Schema) -> dict[str, tuple[Change, ...]]:
    """{table: changes} over the union of both schemas, sorted by table
    name, unchanged tables omitted. Mapping keys must equal Table.name -
    filenames come from the key, statements from the table."""
    return {name: changes
            for name in sorted(set(old) | set(new))
            if (changes := table_diff(old.get(name), new.get(name)))}
