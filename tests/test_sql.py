from ddldelta.diff import (
    AddColumn,
    CreateTable,
    DropColumn,
    DropTable,
    NullabilityChange,
    TypeChange,
)
from ddldelta.model import Column, table_from
from ddldelta.render.sql import column_ddl, statement

META = ('"_DELIVERY" VARCHAR', '"_VALID_FROM" DATE')


def test_column_ddl():
    assert column_ddl(Column("x", "NUMBER(19,4)", True)) == '"x" NUMBER(19,4) NOT NULL'
    assert column_ddl(Column("y", "VARCHAR", False)) == '"y" VARCHAR'


def test_statements_byte_genau_wie_heute():
    table = table_from("A", {"id": ("INT", True), "name": ("VARCHAR(10)", False)})
    assert statement(CreateTable(table), META) == (
        'CREATE TABLE "A" (\n'
        '    "id" INT NOT NULL,\n'
        '    "name" VARCHAR(10),\n'
        '    "_DELIVERY" VARCHAR,\n'
        '    "_VALID_FROM" DATE\n'
        ');')
    assert statement(DropTable("A")) == 'DROP TABLE "A";'
    assert statement(DropColumn("A", "c")) == 'ALTER TABLE "A" DROP COLUMN "c";'
    assert statement(AddColumn("A", Column("neu", "VARCHAR", False))) == (
        'ALTER TABLE "A" ADD COLUMN "neu" VARCHAR;')
    assert statement(TypeChange("A", "id", "INT", "VARCHAR")) == (
        'ALTER TABLE "A" ALTER COLUMN "id" SET DATA TYPE VARCHAR;')
    assert statement(NullabilityChange("A", "id", True)) == (
        'ALTER TABLE "A" ALTER COLUMN "id" SET NOT NULL;')
    assert statement(NullabilityChange("A", "id", False)) == (
        'ALTER TABLE "A" ALTER COLUMN "id" DROP NOT NULL;')
