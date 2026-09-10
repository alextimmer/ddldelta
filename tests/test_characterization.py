"""Byte-level characterization of the generator's outputs.

Freezes the EXACT bytes the generator emits. Deployed V*.sql files are
checksummed by schemachange - any drift here is a breaking change for every
consumer. These expectations must survive the generalization refactor
byte-for-byte; never "fix" an expectation to make a refactor pass.
"""

from ddldelta.generator import (
    GeneratorConfig,
    SupplierConfig,
    generate_supplier,
)

META = ('"_DELIVERY" VARCHAR', '"_VALID_FROM" DATE')


def config_for(tmp_path, **overrides):
    values = dict(
        ddl_dir=tmp_path / "ddl",
        schemachange_dir=tmp_path / "schemachange",
        repo_root=tmp_path,
        account="acc", user="usr", role="rl", warehouse="wh",
        database="DB", metadata_schema="METADATA",
        suppliers={
            "haynespro": SupplierConfig("tsql", "HAYNESPRO_LANDING"),
            "pegase": SupplierConfig("mysql", "PEGASE_LANDING"),
        },
        meta_ddl=META,
        generated_by="test.generator",
        provenance_template="-- generiert von {generated_by} ({comparison}); nicht manuell aendern",
    )
    values.update(overrides)
    return GeneratorConfig(**values)


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


INITIAL_TSQL = (
    "CREATE TABLE [dbo].[KUNDE](\n"
    "    [id] [int] NOT NULL,\n"
    "    [name] [nvarchar](50) NULL,\n"
    "    [preis] [decimal](5, 2) NULL\n"
    ") ON [PRIMARY]\n"
    "GO\n"
)


def test_initial_tsql_create_bytes(tmp_path):
    write(tmp_path / "ddl" / "haynespro" / "2026Q3" / "dbo_KUNDE.sql", INITIAL_TSQL)
    generate_supplier(config_for(tmp_path), "haynespro")
    content = (tmp_path / "schemachange" / "haynespro"
               / "V2026Q3.0001__KUNDE.sql").read_text(encoding="utf-8")
    assert content == (
        "-- generiert von test.generator ((initial) -> 2026Q3); nicht manuell aendern\n"
        'CREATE TABLE "KUNDE" (\n'
        '    "id" INT NOT NULL,\n'
        '    "name" VARCHAR(50),\n'
        '    "preis" DECIMAL(5, 2),\n'
        '    "_DELIVERY" VARCHAR,\n'
        '    "_VALID_FROM" DATE\n'
        ");\n"
    )


def test_initial_tsql_create_bytes_ohne_enforce_not_null(tmp_path):
    write(tmp_path / "ddl" / "haynespro" / "2026Q3" / "dbo_KUNDE.sql", INITIAL_TSQL)
    generate_supplier(config_for(tmp_path, enforce_not_null=False), "haynespro")
    content = (tmp_path / "schemachange" / "haynespro"
               / "V2026Q3.0001__KUNDE.sql").read_text(encoding="utf-8")
    assert content == (
        "-- generiert von test.generator ((initial) -> 2026Q3); nicht manuell aendern\n"
        'CREATE TABLE "KUNDE" (\n'
        '    "id" INT,\n'
        '    "name" VARCHAR(50),\n'
        '    "preis" DECIMAL(5, 2),\n'
        '    "_DELIVERY" VARCHAR,\n'
        '    "_VALID_FROM" DATE\n'
        ");\n"
    )


def test_initial_mysql_create_bytes(tmp_path):
    # Pinnt Display-Width-Dropping (int(11) -> INT) und den kompakten
    # Argument-Separator (decimal(10,2) -> DECIMAL(10,2)) fuer mysql.
    write(tmp_path / "ddl" / "pegase" / "3.46.2" / "artikel.sql",
          "CREATE TABLE artikel (\n"
          "  id int(11) NOT NULL,\n"
          "  preis decimal(10,2) DEFAULT NULL,\n"
          "  PRIMARY KEY (id)\n"
          ");\n")
    generate_supplier(config_for(tmp_path), "pegase")
    content = (tmp_path / "schemachange" / "pegase"
               / "V3.46.2.0001__artikel.sql").read_text(encoding="utf-8")
    assert content == (
        "-- generiert von test.generator ((initial) -> 3.46.2); nicht manuell aendern\n"
        'CREATE TABLE "artikel" (\n'
        '    "id" INT NOT NULL,\n'
        '    "preis" DECIMAL(10,2),\n'
        '    "_DELIVERY" VARCHAR,\n'
        '    "_VALID_FROM" DATE\n'
        ");\n"
    )


def _zwei_lieferungen(tmp_path):
    old_kunde = (
        "CREATE TABLE [dbo].[KUNDE](\n"
        "    [id] [int] NOT NULL,\n"
        "    [name] [nvarchar](50) NULL\n"
        ")\nGO\n")
    new_kunde = (
        "CREATE TABLE [dbo].[KUNDE](\n"
        "    [id] [int] NOT NULL,\n"
        "    [name] [nvarchar](80) NOT NULL,\n"
        "    [neu] [bit] NULL\n"
        ")\nGO\n")
    weg = "CREATE TABLE [dbo].[WEG](\n    [id] [int] NOT NULL\n)\nGO\n"
    write(tmp_path / "ddl" / "haynespro" / "2026Q2" / "dbo_KUNDE.sql", old_kunde)
    write(tmp_path / "ddl" / "haynespro" / "2026Q2" / "dbo_WEG.sql", weg)
    write(tmp_path / "ddl" / "haynespro" / "2026Q3" / "dbo_KUNDE.sql", new_kunde)


def test_delta_kritische_dateien_bytes(tmp_path):
    _zwei_lieferungen(tmp_path)
    generate_supplier(config_for(tmp_path), "haynespro")
    out = tmp_path / "schemachange" / "haynespro"
    head = "-- generiert von test.generator (2026Q2 -> 2026Q3); nicht manuell aendern\n"
    fuse = 'SELECT 1/0 AS "CRITICAL CHANGES DETECTED - PLEASE REVIEW THIS FILE!";\n'
    # Statement-Reihenfolge: Drops (alte Ordnung) zuerst, dann je neuer
    # Spalte Add bzw. Typ- vor Nullability-Aenderung, in DDL-Reihenfolge.
    assert (out / "V2026Q3.0001__KUNDE.sql").read_text(encoding="utf-8") == (
        head + fuse
        + '-- ALTER TABLE "KUNDE" ALTER COLUMN "name" SET DATA TYPE VARCHAR(80);\n'
        + '-- ALTER TABLE "KUNDE" ALTER COLUMN "name" SET NOT NULL;\n'
        + '-- ALTER TABLE "KUNDE" ADD COLUMN "neu" BOOLEAN;\n'
    )
    assert (out / "V2026Q3.0002__WEG.sql").read_text(encoding="utf-8") == (
        head + fuse
        + '-- DROP TABLE "WEG";\n'
    )
    assert (out / "V2026Q3.0000__CRITICAL_CHANGES.sql").read_text(encoding="utf-8") == (
        head
        + 'SELECT 1/0 AS "CRITICAL CHANGES DETECTED - PLEASE REVIEW THE LISTED FILES!";\n'
        + "-- V2026Q3.0001__KUNDE.sql\n"
        + "-- V2026Q3.0002__WEG.sql\n"
    )


def test_config_yml_bytes(tmp_path):
    write(tmp_path / "ddl" / "haynespro" / "2026Q3" / "dbo_KUNDE.sql", INITIAL_TSQL)
    generate_supplier(config_for(tmp_path), "haynespro")
    yml = (tmp_path / "schemachange" / "haynespro"
           / "schemachange-config.yml").read_text(encoding="utf-8")
    assert yml == (
        "# Generated by test.generator (only when missing - edits here stick).\n"
        "# schemachange configuration for the haynespro import (dev). Run from the repo root:\n"
        "#   uv run schemachange deploy --config-folder schemachange/haynespro\n"
        "# NEVER with --create-change-history-table - deploys create no infrastructure;\n"
        "# the history table is a one-time manual bootstrap per supplier\n"
        "# (tools/bootstrap_metadata.py).\n"
        "# Auth deliberately comes from the environment, not from this file: run.py sets\n"
        "# SNOWFLAKE_PASSWORD from SNOWFLAKE_ACCESS_TOKEN (PAT, default authenticator)\n"
        "# or, without a token, SNOWFLAKE_AUTHENTICATOR=externalbrowser (SSO fallback).\n"
        "config-version: 1\n"
        "root-folder: schemachange/haynespro\n"
        "change-history-table: DB.METADATA.SCHEMACHANGE_CHANGE_HISTORY_HAYNESPRO\n"
        "snowflake-account: acc\n"
        "snowflake-user: usr\n"
        "snowflake-role: rl\n"
        "snowflake-warehouse: wh\n"
        "snowflake-database: DB\n"
        "snowflake-schema: HAYNESPRO_LANDING\n"
        "query-tag: haynespro-schemachange\n"
    )
