import sqlglot

from ddldelta.ddl_parser import parser_for
from ddldelta.types import SNOWFLAKE, TypeMapping


def _kind(sql, dialect):
    """Der sqlglot-Typknoten der ersten Spalte eines CREATE TABLE."""
    create = sqlglot.parse_one(sql, read=dialect)
    return create.this.expressions[0].args["kind"]


def test_snowflake_default_mappt_wie_bisher():
    assert SNOWFLAKE.render(_kind("CREATE TABLE t (c datetime)", "tsql"), "tsql") == "TIMESTAMP_NTZ"
    assert SNOWFLAKE.render(_kind("CREATE TABLE t (c nvarchar(50))", "tsql"), "tsql") == "VARCHAR(50)"
    assert SNOWFLAKE.render(_kind("CREATE TABLE t (c decimal(5, 2))", "tsql"), "tsql") == "DECIMAL(5, 2)"
    assert SNOWFLAKE.render(_kind("CREATE TABLE t (c decimal(10,2))", "mysql"), "mysql") == "DECIMAL(10,2)"
    assert SNOWFLAKE.render(_kind("CREATE TABLE t (c int(11))", "mysql"), "mysql") == "INT"


def test_eigenes_mapping_ist_injizierbar():
    postgresish = TypeMapping(
        renames={"DATETIME": "TIMESTAMP"},
        keep_args=frozenset({"VARCHAR"}),
    )
    parse = parser_for("mysql", mapping=postgresish)
    _, columns, _ = parse("CREATE TABLE t (a datetime, b varchar(9), c decimal(5,2))")
    assert columns == {
        "a": ("TIMESTAMP", False),
        "b": ("VARCHAR(9)", False),
        "c": ("DECIMAL", False),   # DECIMAL nicht in keep_args -> Args fallen weg
    }
