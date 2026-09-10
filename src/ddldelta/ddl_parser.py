# DDL parser per supplier dialect, built on sqlglot. Shared result format:
# (table_name, {column: (snowflake_type, not_null)}, key) - columns in
# definition order, names in the DDL's original spelling (decision 3),
# key = PRIMARY KEY columns as a tuple in DDL order (empty if none).
# Consumers: create_schemachange_files (generator, ignores the key) and the
# load_blob_to_landing preflight (position check of the positional COPY;
# the key feeds the historization diff).
# Design: plan 2026-08-20; keys: plan 2026-08-25 (bitemporal);
# sqlglot: plan 2026-08-25-ddl-parser-sqlglot.
#
# Why a library: a new supplier's dialect is a string here, not a new pair of
# regexes. What stays ours is the target type mapping - sqlglot's Snowflake
# generator emits types Snowflake does not have (UINT, ENUM, ...); it is built
# for queries, not for DDL migration. The mapping itself lives in types.py
# (TypeMapping) - injectable, the default here is the historical SNOWFLAKE one.

from collections.abc import Callable

import sqlglot
from sqlglot import exp

from ddldelta.types import SNOWFLAKE, TypeMapping

# Every dialect sqlglot can read - the set a new supplier may pick from.
DIALECTS = {d.value for d in sqlglot.dialects.Dialects if d.value}

# table_name, {column: (snowflake_type, not_null)}, key - see module docstring.
ParseResult = tuple[str, dict[str, tuple[str, bool]], tuple[str, ...]]


def snowflake_type(kind: exp.DataType, dialect: str = "mysql") -> str:
    """sqlglot type node (exp.DataType) -> Snowflake type string."""
    return SNOWFLAKE.render(kind, dialect)


def _statements(text: str, dialect: str) -> list[sqlglot.Expr]:
    """Parsed statements. T-SQL scripts are GO-separated batches; sqlglot does
    not know GO and would silently degrade the whole file to one Command node.
    """
    parts = [p for p in text.split("\nGO") if p.strip()] if dialect == "tsql" else [text]
    out: list[sqlglot.Expr] = []
    for part in parts:
        out.extend(s for s in sqlglot.parse(part, read=dialect) if s is not None)
    return out


def _key_from_constraints(statements: list[sqlglot.Expr]) -> tuple[str, ...]:
    """PRIMARY KEY columns from a separate ALTER TABLE ... ADD CONSTRAINT.

    T-SQL scripts declare the key that way. sqlglot builds no exp.PrimaryKey
    for it - the column list hangs in a ClusteredColumnConstraint next to a
    PrimaryKeyColumnConstraint (measured 2026-08-25, sqlglot 30.17). Pinned by
    test_sqlserver_pk_aus_alter_constraint so a sqlglot update cannot change
    this unnoticed.
    """
    for statement in statements:
        if not isinstance(statement, exp.Alter):
            continue
        for constraint in statement.find_all(exp.Constraint):
            kinds = constraint.expressions
            if not any(isinstance(k, exp.PrimaryKeyColumnConstraint) for k in kinds):
                continue
            for kind in kinds:
                if isinstance(kind, exp.ClusteredColumnConstraint):
                    return tuple(c.name for c in kind.find_all(exp.Column))
    return ()


def parse(text: str, dialect: str, mapping: TypeMapping = SNOWFLAKE) -> ParseResult:
    """DDL text -> (table_name, {column: (snowflake_type, not_null)}, key).

    Raises ValueError if the text holds no usable CREATE TABLE - sqlglot
    degrades unknown syntax to a Command node instead of raising, and a silent
    empty column list would reach the generator and the positional COPY.
    """
    try:
        statements = _statements(text, dialect)
    except Exception as error:                       # sqlglot ParseError & co.
        raise ValueError("unparseable DDL (" + dialect + "): " + str(error)) from None
    create = next((s for s in statements
                   if isinstance(s, exp.Create) and isinstance(s.this, exp.Schema)), None)
    if create is None:
        raise ValueError("no CREATE TABLE found (expected " + dialect + " DDL)")

    table = create.this.this.name
    columns: dict[str, tuple[str, bool]] = {}
    key: tuple[str, ...] = ()
    for element in create.this.expressions:
        if isinstance(element, exp.ColumnDef):
            constraints = [c.kind for c in element.constraints]
            # An explicit NULL is also a NotNullColumnConstraint in sqlglot -
            # it carries allow_null=True. Testing the class alone would mark
            # every explicitly nullable T-SQL column as NOT NULL.
            not_null = any(isinstance(c, exp.NotNullColumnConstraint)
                           and not c.args.get("allow_null") for c in constraints)
            if any(isinstance(c, exp.PrimaryKeyColumnConstraint) for c in constraints):
                key += (element.name,)
            columns[element.name] = (mapping.render(element.args["kind"], dialect),
                                     not_null)
        elif isinstance(element, exp.PrimaryKey):    # table constraint (MySQL)
            key = tuple(c.name for c in element.expressions)
    if not columns:
        raise ValueError("CREATE TABLE without columns (expected " + dialect + " DDL)")
    return table, columns, key or _key_from_constraints(statements)


def parser_for(dialect: str, mapping: TypeMapping = SNOWFLAKE) -> Callable[[str], ParseResult]:
    """Parse function for a sqlglot dialect name.

    THE extension point for a new supplier: an entry in suppliers.py, no code
    here. An unknown dialect fails at once (typo in the registry) instead of
    at the first delivery.
    """
    if sqlglot.Dialect.get(dialect) is None:
        raise ValueError(
            "unknown SQL dialect " + repr(dialect)
            + " - valid values: " + ", ".join(sorted(DIALECTS)))
    return lambda text: parse(text, dialect, mapping)


def parse_sqlserver_ddl(text: str) -> ParseResult:
    """SQL Server DDL (SSMS script, GO-separated batches)."""
    return parse(text, "tsql")


def parse_mysql_ddl(text: str) -> ParseResult:
    """MySQL dump per table (one mysqldump-style CREATE TABLE per file)."""
    return parse(text, "mysql")
