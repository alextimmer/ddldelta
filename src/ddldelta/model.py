# The neutral schema model everything flows through: sources produce it,
# the diff compares it, renderers consume changes over it. Types are
# TARGET-dialect strings (the TypeMapping is applied at parse time).

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace


@dataclass(frozen=True)
class Column:
    name: str
    type: str
    not_null: bool


@dataclass(frozen=True)
class Table:
    name: str
    columns: tuple[Column, ...]
    key: tuple[str, ...] = ()

    @property
    def columns_by_name(self) -> dict[str, Column]:
        """Columns keyed by name, insertion order preserved; assumes unique
        column names (a parser bug producing duplicates would silently keep
        the last)."""
        return {c.name: c for c in self.columns}


type Schema = Mapping[str, Table]


def table_from(name: str, columns: Mapping[str, tuple[str, bool]],
               key: Iterable[str] = ()) -> Table:
    """Table from the parser's result format {column: (type, not_null)}."""
    return Table(name, tuple(Column(n, t, nn) for n, (t, nn) in columns.items()),
                 tuple(key))


def without_nullability(schema: Schema) -> dict[str, Table]:
    """Schema with nullability stripped from every column.

    Replaces the old enforce_not_null=False mode as model normalization:
    no NOT NULL reaches any rendered statement, nullability-only changes
    vanish from the diff, and a new NOT NULL column stops being critical.
    """
    return {name: replace(table, columns=tuple(
                replace(column, not_null=False) for column in table.columns))
            for name, table in schema.items()}
