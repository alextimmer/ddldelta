# Curated public API of the package; repo-internal consumers keep importing
# from the submodules (from ddldelta.ddl_parser import ...).

from ddldelta.change_history import (
    CHANGE_HISTORY_COLUMNS,
    change_history_table,
)
from ddldelta.ddl_parser import (
    DIALECTS,
    ParseResult,
    parse,
    parse_mysql_ddl,
    parse_sqlserver_ddl,
    parser_for,
)
from ddldelta.diff import (
    AddColumn,
    Change,
    CreateTable,
    DropColumn,
    DropTable,
    NullabilityChange,
    TypeChange,
    schema_diff,
    table_diff,
)
from ddldelta.errors import GenerationError
from ddldelta.generator import (
    GeneratorConfig,
    SupplierConfig,
    SupplierResult,
    generate_supplier,
    schemachange_config,
)
from ddldelta.model import Column, Schema, Table, table_from, without_nullability
from ddldelta.plan import MigrationPlan, Renderer, TablePlan, baseline_plan, build_plan
from ddldelta.policy import ChangePolicy, FusePolicy, Severity
from ddldelta.render.files import (
    CRITICAL_FILE_HEADER,
    CRITICAL_SUMMARY_HEADER,
    META_PREFIX,
    PROVENANCE_TEMPLATE,
    provenance,
    write_generated,
    write_plan,
)
from ddldelta.render.flyway import FlywayRenderer
from ddldelta.render.jinja import JinjaRenderer
from ddldelta.render.report import CompatibilityReport, Finding, build_report
from ddldelta.render.schemachange import SchemachangeRenderer
from ddldelta.render.sql import column_ddl, statement
from ddldelta.snapshot import (
    SnapshotSource,
    load_snapshot,
    save_snapshot,
    schema_from_dict,
    schema_to_dict,
)
from ddldelta.sources import (
    DeliveryDirectorySource,
    PairSource,
    PathPairSource,
    SchemaPair,
    parse_path,
    rows_to_schema,
)
from ddldelta.types import SNOWFLAKE, TypeMapping

__all__ = [
    "AddColumn",
    "CHANGE_HISTORY_COLUMNS",
    "CRITICAL_FILE_HEADER",
    "CRITICAL_SUMMARY_HEADER",
    "Change",
    "ChangePolicy",
    "Column",
    "CompatibilityReport",
    "CreateTable",
    "DIALECTS",
    "DeliveryDirectorySource",
    "DropColumn",
    "DropTable",
    "Finding",
    "FlywayRenderer",
    "FusePolicy",
    "GenerationError",
    "GeneratorConfig",
    "JinjaRenderer",
    "META_PREFIX",
    "MigrationPlan",
    "NullabilityChange",
    "PROVENANCE_TEMPLATE",
    "PairSource",
    "ParseResult",
    "PathPairSource",
    "Renderer",
    "SNOWFLAKE",
    "Schema",
    "SchemaPair",
    "SchemachangeRenderer",
    "Severity",
    "SnapshotSource",
    "SupplierConfig",
    "SupplierResult",
    "Table",
    "TablePlan",
    "TypeChange",
    "TypeMapping",
    "baseline_plan",
    "build_plan",
    "build_report",
    "change_history_table",
    "column_ddl",
    "generate_supplier",
    "load_snapshot",
    "parse",
    "parse_mysql_ddl",
    "parse_path",
    "parse_sqlserver_ddl",
    "parser_for",
    "provenance",
    "rows_to_schema",
    "save_snapshot",
    "schema_diff",
    "schema_from_dict",
    "schema_to_dict",
    "schemachange_config",
    "statement",
    "table_diff",
    "table_from",
    "without_nullability",
    "write_generated",
    "write_plan",
]
