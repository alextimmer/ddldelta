# Typed change -> target SQL statement. The exact strings are a byte
# contract: deployed migrations were generated from these templates and are
# checksummed by schemachange.

from collections.abc import Sequence

from ddldelta.diff import (
    AddColumn,
    Change,
    CreateTable,
    DropColumn,
    DropTable,
    NullabilityChange,
    TypeChange,
)
from ddldelta.model import Column


def column_ddl(column: Column) -> str:
    return f'"{column.name}" {column.type}' + (" NOT NULL" if column.not_null else "")


def statement(change: Change, meta_ddl: Sequence[str] = ()) -> str:
    """One SQL statement per change; meta_ddl lines trail CREATE TABLE."""
    match change:
        case CreateTable(table=table):
            columns = ",\n    ".join(
                [column_ddl(c) for c in table.columns] + list(meta_ddl))
            return f'CREATE TABLE "{table.name}" (\n    {columns}\n);'
        case DropTable(name=name):
            return f'DROP TABLE "{name}";'
        case DropColumn(table=table, column=column):
            return f'ALTER TABLE "{table}" DROP COLUMN "{column}";'
        case AddColumn(table=table, column=column):
            return f'ALTER TABLE "{table}" ADD COLUMN {column_ddl(column)};'
        case TypeChange(table=table, column=column, new_type=new_type):
            return f'ALTER TABLE "{table}" ALTER COLUMN "{column}" SET DATA TYPE {new_type};'
        case NullabilityChange(table=table, column=column, not_null=not_null):
            action = "SET NOT NULL" if not_null else "DROP NOT NULL"
            return f'ALTER TABLE "{table}" ALTER COLUMN "{column}" {action};'
    raise TypeError(f"unknown change type: {change!r}")
