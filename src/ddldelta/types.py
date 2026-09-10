# Target-dialect type mapping, applied at PARSE time: the diff compares the
# mapped types, so arg-dropping (mysql int(11) vs int(10) -> both "INT" ->
# no change) is part of the comparison semantics. Mapping at render time
# would produce false criticals and byte drift.

from collections.abc import Mapping
from dataclasses import dataclass, field

from sqlglot import exp


@dataclass(frozen=True)
class TypeMapping:
    """Maps sqlglot type names (exp.DataType.Type) to target type strings.

    renames only maps deviations; everything else passes through as a
    target-dialect synonym - unknown types fail loudly at deploy time.
    Only keep_args types keep their precision/length arguments (display
    widths, 'max', enum value lists carry no meaning for the target).
    arg_separators is per SOURCE dialect - purely cosmetic, but generated
    migrations must stay byte-reproducible (SSMS writes DECIMAL(5, 2),
    mysqldump writes decimal(10,2)).
    """
    renames: Mapping[str, str]
    keep_args: frozenset[str]
    arg_separators: Mapping[str, str] = field(default_factory=dict)

    def render(self, kind: exp.DataType, dialect: str) -> str:
        """sqlglot type node (exp.DataType) -> target type string."""
        mapped = self.renames.get(kind.this.name, kind.this.name)
        args = [e.name for e in kind.expressions if e.name.isdigit()]
        if args and mapped in self.keep_args:
            mapped += "(" + self.arg_separators.get(dialect, ",").join(args) + ")"
        return mapped


# The historical Snowflake mapping - values verbatim from ddl_parser.py;
# deployed migrations depend on it.
SNOWFLAKE = TypeMapping(
    renames={
        "BIT": "BOOLEAN",       # bit columns exported as true/false -> BOOLEAN fits
        "DATETIME": "TIMESTAMP_NTZ",
        "DATETIME2": "TIMESTAMP_NTZ",
        "SMALLDATETIME": "TIMESTAMP_NTZ",
        "MONEY": "NUMBER(19,4)",
        "SMALLMONEY": "NUMBER(10,4)",
        "NVARCHAR": "VARCHAR",
        "NCHAR": "CHAR",
        "TEXT": "VARCHAR",
        "MEDIUMTEXT": "VARCHAR",
        "LONGTEXT": "VARCHAR",
        "IMAGE": "BINARY",
        "UUID": "VARCHAR(36)",  # tsql uniqueidentifier, postgres uuid
        "DOUBLE": "FLOAT",
        "ENUM": "VARCHAR",      # the supplier's value list is not mirrored
        "SET": "VARCHAR",
        "MEDIUMINT": "INT",     # no Snowflake synonym
        "UMEDIUMINT": "INT",
        "UINT": "INT",
        "UBIGINT": "BIGINT",
        "UTINYINT": "TINYINT",
        "USMALLINT": "SMALLINT",
        "UDECIMAL": "DECIMAL",   # MySQL unsigned decimal
        "UDOUBLE": "FLOAT",
    },
    keep_args=frozenset({"VARCHAR", "CHAR", "NUMBER", "DECIMAL", "NUMERIC", "BINARY", "VARBINARY"}),
    arg_separators={"tsql": ", "},
)
