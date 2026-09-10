# ddldelta

## What it is

ddldelta is an offline migration-plan generator. It compares two states of a
SQL schema — each state a directory of `CREATE TABLE` files, in whatever
dialect a third party happens to deliver (T-SQL, MySQL, or any of the other
dialects sqlglot can read) — and turns the difference into versioned
migrations for [schemachange](https://github.com/Snowflake-Labs/schemachange)
or [Flyway](https://flywaydb.org/), or into a CI compatibility report.

The source of truth is the delivered DDL files themselves, not a live
database: ddldelta never opens a database connection, needs no credentials,
and needs no network access. Given the same two DDL directories it always
produces the same bytes, which makes it safe to run in CI: no side effects,
deterministic output, and a process exit code (via the report mode) that a
pipeline can gate on. *Applying* the generated migrations remains
schemachange's or Flyway's job — ddldelta only plans.

## What it is not

ddldelta is not a declarative live-database convergence tool. It does not
connect to a database, does not introspect a running schema, and does not
compute "what statements turn the live database into this target state" the
way Atlas or SnowDDL do — its two inputs are always DDL files, and its output
is always a migration plan, not an applied change.

It also does not detect renames. The old and new schema are compared by
column name in a plain dict: a column that a supplier renamed shows up as a
drop of the old name plus an add of the new one, and a dropped-and-added
column is critical (see below) even though no data would actually be lost by
a real rename. This is deliberate — inferring a rename from a diff is a
guess, and a wrong guess silently discards a column under a guessed identity
instead of correctly protecting it behind the fuse.

Nor does it diff primary keys. The DDL parser extracts each table's key
(`Table.key`) and it round-trips through snapshots, but `schema_diff`
compares columns only — a delivery that adds, drops, or swaps primary-key
columns produces no `Change`, and therefore no fuse, no migration statement,
and no compatibility-report finding. This is deliberate too, not a gap
waiting to be closed casually: keys were never part of generated DDL
(migrations are column-only), so adding key comparison to the default diff
would retroactively re-fuse every past delivery that ever touched a primary
key, breaking the promise that regenerating against unchanged inputs is a
no-op. Today, a primary-key/grain change passes `ddldelta check` silently —
see decision D08 in `docs/decisions.md` for the rationale and the opt-in
extension this would need.

## Documentation

This README covers usage. The design rationale behind the architecture and
safety model, and a decision-by-decision log (including what was
deliberately deferred and why), live under `docs/`:

- [`docs/design.md`](docs/design.md) — positioning, architecture, the three
  extension seams, the safety model, and the reasoning behind type mapping
  happening at parse time.
- [`docs/decisions.md`](docs/decisions.md) — an ADR-style log of every
  significant choice, including revisions and the full deferred-until-
  release list.

Interactive tutorials live in [`examples/`](examples/): `01_quickstart.ipynb`
walks through parsing, the compatibility check, and the fuse;
`02_workflow_snapshots_cli.ipynb` covers the operational workflow —
snapshots, the command line, and baselines; `03_jinja_scaffolding.ipynb`
generates per-table schemachange scripts from a shared Jinja macro via
`JinjaRenderer`. The `src` layout keeps them out of the installed wheel; run
them with any Jupyter, e.g. `uv run --with jupyter jupyter lab examples/`.

## Safety model

Two mechanisms keep a bad migration from ever reaching a database unnoticed.

**The fuse.** Every change is classified `SAFE` or `CRITICAL` by a
`ChangePolicy` (the default, `FusePolicy`, ships in `policy.py`). Table
drops, column drops, type changes, NOT-NULL additions, and nullability
changes are always critical; a new nullable column or a brand-new table are
safe. A table with even one critical change is rendered entirely as SQL
*comments* behind a leading `SELECT 1/0 AS "CRITICAL CHANGES DETECTED...";`
statement, plus a `V<label>.0000__CRITICAL_CHANGES.sql` file summarizing
every affected table for that delivery. The `SELECT 1/0` is not a bug to
work around: it makes the migration fail deployment on purpose, so a human
has to open the file, read the commented-out statements, and uncomment (or
rewrite) them deliberately before anything critical can run.

**The exists-guard.** Once a migration file has been written and deployed,
schemachange checksums it — rewriting it invalidates every future deploy.
ddldelta therefore never overwrites a file that already exists on disk. When
asked to write a target that is already there, it compares the *supplier
facts* of the new content against the existing file (everything except the
leading provenance line and any meta-column lines): identical facts mean the
run was idempotent and it silently skips the write; a real divergence raises
`GenerationError` and stops rather than silently corrupting a deployed file.

## Architecture & extension points

```
PairSource.load() -> SchemaPair (old Schema, new Schema)
    |  parsed via ddl_parser.parser_for(dialect), TypeMapping applied at parse time
    v
schema_diff(old, new)            -> {table: (Change, ...)}      (diff.py)
    v
build_plan(..., policy)          -> MigrationPlan(TablePlan...)  (plan.py)
    v
Renderer.render(plan)            -> tuple[Path, ...]

    (report mode is a separate branch off the schema pair, not a Renderer:)
SchemaPair.old/new -> build_report(comparison, old, new, policy)
                      -> CompatibilityReport (render/report.py, writes nothing)
```

| Module | Role |
| --- | --- |
| `sources.py` | `PairSource` protocol; `DeliveryDirectorySource` reads `<supplier>/<delivery>/*.sql` directories, newest two by lexicographic name; `PathPairSource` takes two explicit paths (no naming convention); `parse_path` parses one schema state (a directory or a single `.sql` file) and is public on its own; `rows_to_schema` builds a `Schema` from pre-ordered `(table, column, type, not_null)` rows instead of a DB connection (see "Working from a live catalog" below) |
| `snapshot.py` | `save_snapshot` / `load_snapshot`: a parsed `Schema` as versioned JSON (format v1, marker `ddldelta_snapshot`); `SnapshotSource` is a `PairSource` that diffs a DDL path against a stored snapshot instead of a second DDL directory — a missing snapshot file is the bootstrap case (initial state) unless `require_snapshot=True`, which fails fast on a missing file instead |
| `model.py` | The neutral `Schema` / `Table` / `Column` value types every stage shares; `without_nullability` strips nullability as a model normalization |
| `types.py` | `TypeMapping`: sqlglot type name → target-dialect type string, applied at parse time (not render time) |
| `ddl_parser.py` | `parse` / `parser_for` over sqlglot; dialect-specific quirks (T-SQL `GO` batching, primary keys hanging off `ALTER TABLE ... ADD CONSTRAINT`) are pinned here |
| `diff.py` | `table_diff` / `schema_diff`: pure structural comparison into typed `Change` values — no SQL, no severity |
| `policy.py` | `ChangePolicy` protocol; `FusePolicy`, the default, classifies each `Change` as `Severity.SAFE` or `Severity.CRITICAL` |
| `plan.py` | `build_plan`: bundles the diff with policy verdicts into a `MigrationPlan` of `TablePlan`s; `baseline_plan` diffs an empty schema against the current state for a fresh CREATE-only baseline; defines the `Renderer` protocol |
| `render/sql.py` | `statement` / `column_ddl`: one `Change` → one SQL statement string (a byte contract — see Invariants) |
| `render/files.py` | Shared file mechanics: provenance line, the exists-guard, the fuse headers, versioned `V<label>.<NNNN>__<table>.sql` naming |
| `render/schemachange.py` | `SchemachangeRenderer`: thin `Renderer` over `render/files.write_plan` |
| `render/flyway.py` | `FlywayRenderer`: same file mechanics, but validates that `plan.label` is a Flyway-legal numeric version first |
| `render/jinja.py` | `JinjaRenderer` (optional, `jinja` extra): a user-supplied Jinja template decides file content from plan/schema context; overwrites on every render instead of using the exists-guard — see "Using ddldelta alongside schemachange's Jinja features" |
| `render/report.py` | `build_report` / `CompatibilityReport`: writes nothing, just answers "is the new delivery backward compatible?" with a process exit code |
| `generator.py` | `generate_supplier` / `GeneratorConfig`: the schemachange-specific convenience orchestration (source → plan → `SchemachangeRenderer`, plus the per-supplier `schemachange-config.yml`) |
| `change_history.py` | The schemachange change-history table naming convention and its expected columns |
| `errors.py` | `GenerationError`, the one exception the package raises to signal an abort condition |
| `cli.py` | `main(argv) -> int`, the `ddldelta` console script (`check`, `generate`, `baseline`, `snapshot`); the only module allowed to print or return a process exit code — the core stays log-free and never exits |

ddldelta has three seams meant for extension, each a `Protocol` rather than a
base class to subclass.

**`PairSource`** — supply schema states from somewhere other than delivery
directories (a database snapshot, an `information_schema` dump, ...) by
implementing `.load() -> SchemaPair | None`. A smaller, common case is
customizing how the *existing* source parses: pass a project-specific
`TypeMapping` into the dialect parser instead of the default Snowflake one.

```python
from ddldelta.ddl_parser import parser_for
from ddldelta.types import TypeMapping

postgres_types = TypeMapping(renames={"INT4": "INTEGER"}, keep_args=frozenset({"VARCHAR"}))
parse_ddl = parser_for("postgres", mapping=postgres_types)
```

A second, simpler source ships out of the box for the common case where
"old" and "new" are just two paths you already know, with no delivery-
directory naming convention to infer them from: `PathPairSource`. Each of
`old`/`new` may be a directory of `*.sql` files or a single `.sql` file
(one table); `old=None` means an initial state (every table is new).

```python
from ddldelta.sources import PathPairSource

pair = PathPairSource(Path("schema/v1"), Path("schema/v2"), parse_ddl).load()
```

**Working from a live catalog without a DB connection.** `rows_to_schema`
builds a `Schema` from an iterable of `(table, column, type, not_null)`
rows — the shape an `information_schema` query naturally returns — without
this package ever opening a connection itself; the caller runs the query.
Rows must already be grouped consecutively by table (matching how such a
query is normally ordered): a table name that reappears later, after a
different table's rows, raises `GenerationError` rather than silently
discarding the columns collected the first time.

```python
from ddldelta.sources import rows_to_schema

rows = [("KUNDE", "id", "INT", True), ("KUNDE", "name", "VARCHAR", False)]
schema = rows_to_schema(rows)
```

Caveat: a live catalog's own type spellings (e.g. a warehouse reporting
`TEXT` or `NUMBER(38,0)`) usually differ from what this package's own
`TypeMapping` would produce for the same logical type. Normalize types on
the caller side before diffing against a `rows_to_schema` result, or the
diff will report false `TypeChange` findings.

**`ChangePolicy`** — swap what counts as critical by implementing
`.classify(change) -> Severity` and injecting it, e.g. through
`GeneratorConfig(policy=...)`:

```python
from dataclasses import dataclass
from ddldelta.generator import GeneratorConfig
from ddldelta.policy import Severity

@dataclass(frozen=True)
class LenientPolicy:
    def classify(self, change):
        return Severity.SAFE   # never fuse - e.g. for a throwaway dev schema

config = GeneratorConfig(..., policy=LenientPolicy())
```

**`Renderer`** — produce something other than versioned migration files.
`render/report.py` is itself a worked example: it consumes the same diff and
policy as the file renderers, but returns a value object with a CI-friendly
exit code instead of writing anything:

```python
from ddldelta.diff import schema_diff  # unused here, shown for context
from ddldelta.policy import FusePolicy
from ddldelta.render.report import build_report

report = build_report(pair.comparison, pair.old, pair.new, FusePolicy())
print(report.text())
raise SystemExit(report.exit_code)   # 0 compatible, 1 a critical change was found
```

## Quickstart

```python
from pathlib import Path

from ddldelta.generator import GeneratorConfig, SupplierConfig, generate_supplier

config = GeneratorConfig(
    ddl_dir=Path("ddl"),                    # ddl/<supplier>/<delivery>/*.sql
    schemachange_dir=Path("schemachange"),  # schemachange/<supplier>/V*.sql + yml
    repo_root=Path("."),                    # yml root-folder is rendered relative to this
    account="myaccount", user="svc_user", role="loader_role",
    warehouse="loader_wh", database="RAW", metadata_schema="METADATA",
    suppliers={
        "acme": SupplierConfig(dialect="tsql", landing_schema="ACME_LANDING"),
    },
    meta_ddl=('"_DELIVERY" VARCHAR', '"_VALID_FROM" DATE'),
    generated_by="acme_pipeline.generate",
)

result = generate_supplier(config, "acme")
print(result.delivery, result.comparison, result.written)
```

`generate_supplier` reads the newest two delivery directories under
`ddl_dir/acme`, writes a `schemachange-config.yml` on first run only, and
writes one migration per changed table (idempotent per delivery — a rerun
against the same deliveries writes nothing new).

## Invariants

- **Byte-identity.** The exact bytes of a generated migration are a
  contract: once deployed, schemachange has checksummed the file, so
  regenerating it must reproduce the same bytes or not touch it at all.
  This is what the characterization tests pin down.
- **The provenance template is injectable** (`provenance_template`,
  default English, e.g. `"-- generated by {generated_by} ({comparison});
  do not edit manually"`) so a consumer with an existing, differently-worded
  corpus of deployed files can keep them byte-identical. The exists-guard's
  facts filter derives the line prefix it matches from this template, and
  strips *only* a matching provenance line at line 0 of the file — never a
  line anywhere else. A foreign corpus that puts provenance somewhere other
  than line 0 is therefore treated as diverging content on the next run
  (`GenerationError`), not silently mismatched: a loud failure rather than a
  quietly wrong comparison.
- **`enforce_not_null=False` is model normalization, not a rendering
  option.** It strips nullability from every column before the diff runs
  (`model.without_nullability`), so no `NOT NULL` ever reaches a rendered
  statement and a nullability-only change stops existing as a change at all.
  Because this changes what counts as a supplier fact, flipping the flag
  changes the bytes of every migration regenerated afterward — treat it as
  a one-time decision made together with a full rebuild, not a toggle.
- **Flyway version labels must be numeric.** `FlywayRenderer` validates
  `plan.label` against Flyway's version grammar (digits separated by `.` or
  `_`) before rendering and raises `GenerationError` otherwise; a
  non-numeric delivery label (e.g. `"2026Q3"`) must be mapped to a numeric
  version by the caller first.

## Command line

`packages/ddldelta` ships a console script, `ddldelta`, registered via
`project.scripts` in `pyproject.toml` (`uv sync` installs it). It is a thin
wrapper: same four stages as the library (parse → diff → policy → render),
just callable without writing Python. All positional/optional schema-state
arguments (`OLD`, `NEW`, `--old`) accept a directory of `*.sql` files, a
single `.sql` file, or a `.json` ddldelta snapshot (auto-detected by the
`.json` suffix).

```
ddldelta check    --dialect D OLD NEW [--json]
ddldelta generate --dialect D --label L --out DIR NEW [--old PATH] [--generated-by S] [--flyway] [--snapshot FILE]
ddldelta baseline --dialect D --label L --out DIR NEW [--generated-by S] [--flyway]
ddldelta snapshot --dialect D --label L --out FILE NEW
```

**`check`** — the CI gate: prints a compatibility report (`text()` by
default, `to_json()` with `--json`) and exits accordingly. No files written.

```
ddldelta check --dialect tsql ddl/acme/2026Q2 ddl/acme/2026Q3
```

Honest caveat for a CI gate: `check` reports column changes only — a
primary-key/grain change (see "What it is not" above) is not a `Change` at
all, so it passes with exit code `0` and no finding, silently. Do not rely
on `ddldelta check` alone to catch a supplier changing a table's grain.

**`generate`** — renders versioned migration files for the diff between two
states; `--old` omitted means an initial migration (every table is new).

```
ddldelta generate --dialect tsql --label 2026Q3 \
    --out schemachange/acme --old ddl/acme/2026Q2 ddl/acme/2026Q3
```

**`baseline`** — the current state as a fresh CREATE-only migration set (no
`--old`), for a new environment or a Flyway/schemachange rebaseline.

**`snapshot`** — persists a parsed schema state as JSON, for a workflow with
no delivery directories to diff against later.

**The snapshot workflow.** When there is nothing to keep an old DDL
directory around for (e.g. the source is a one-shot export, not a series of
numbered deliveries), pass `--snapshot FILE` to `generate` — it saves the
*new* state there after a successful render. The next run then points
`--old` at that same file instead of an old DDL directory:

```
ddldelta generate --dialect mysql --label 2026Q3 --out out/ new/ --snapshot state.json
# ... later, once "new/" has moved on ...
ddldelta generate --dialect mysql --label 2026Q4 --out out/ new/ --old state.json --snapshot state.json
```

The snapshot format is versioned JSON (`snapshot.py`, `SNAPSHOT_VERSION`) —
a future format change is rejected with a clear error instead of silently
misread.

**Exit codes**: `0` — ok, or `check` found no critical change; `1` —
`check` found at least one critical change; `2` — an error (unknown
dialect, an unreadable/invalid path or snapshot, a `--flyway` label that
is not numeric, ...); the message is printed to stderr as `error: ...`. An
unexpected exception is caught at the top level and also mapped to `2`,
never to `1` — that code is reserved exclusively for `check`'s deliberate
finding, so a crash can never be mistaken for a compatibility result by a
script reading only the exit code.

A fused table is deliberately *not* a `generate`/`baseline` error — the
`SELECT 1/0` fuse is schemachange's/Flyway's deploy-time gate, not this
command's — so the exit code stays `0` even when a critical change was
rendered. To keep that from being silently missed in a script, `generate`
and `baseline` print `N critical table(s) fused - review required` to
stderr whenever `plan.critical_tables` is non-empty, without changing the
exit code.

**Library-only knobs.** The CLI intentionally does not expose everything
the library can do: meta-column DDL, a custom provenance template, a
custom `ChangePolicy`, `generate_supplier`'s `GeneratorConfig`/
`schemachange-config.yml` orchestration, or `SnapshotSource` (with its
bootstrap-on-missing default and `require_snapshot=True` opt-in). Note the
CLI never bootstraps from a missing snapshot: a `.json` path that does not
exist is always an error (exit 2). Reach for the Python API (see
Quickstart below) when you need those.

## Using ddldelta alongside schemachange's Jinja features

schemachange renders every script it deploys (`V__`, `R__`, `A__`) through
its own Jinja engine before running it, and executes them in `V` → `R` →
`A` order. Two things follow from that for a ddldelta user.

**Coexistence.** ddldelta's generated migrations are Jinja-*inert* plain
SQL: they contain no `{{ }}`/`{% %}` syntax, so schemachange's Jinja pass
renders them unchanged and they run exactly as generated. This means
hand-written, Jinja-heavy `A__`/`R__` scripts — for example a shared macro
module and a set of scripts that call it to parametrize COPY INTO
workloads — can live in the very same `root-folder` as ddldelta's
generated `V__` files without any conflict. ddldelta only ever writes files
matching its own `V<label>.<NNNN>__<table>.sql` pattern, and its
exists-guard only ever compares *those* files against themselves; it has
no opinion about anything else schemachange finds under the same root.
`generate_supplier` also writes the per-supplier `schemachange-config.yml`
only when it does not already exist, specifically so that a `modules-folder:`
or `vars:` block added by hand for those macro scripts survives every
future regeneration.

One nuance worth knowing before it surprises you: schemachange checksums
the *rendered* result of an `R__` script, not its source text. Editing a
shared macro therefore re-triggers every `R__` script that calls it on the
next deploy, even though none of those scripts' own files changed.

**Templated input DDL is unsupported.** The other direction — Jinja syntax
inside the *vendor-delivered* DDL this package parses — is not something
`ddl_parser` handles. An un-rendered `{{ }}` placeholder in a `CREATE TABLE`
file fails loudly as `unparseable DDL` rather than being silently
mis-parsed; render the template yourself before handing the result to
`PairSource`/`parse_path`. A `preprocess` hook on the parser that would do
this rendering for you is deliberately deferred until a real consumer needs
it — see decision D12 in `docs/decisions.md`.

**Templated output is a custom-renderer concern.** When what you actually
want is the *reverse* of the coexistence case above — not writing
Jinja-heavy scripts by hand, but *generating* them from the current schema
— that is what the optional `JinjaRenderer` (`ddldelta.render.jinja`,
requires the `jinja` extra: `pip install ddldelta[jinja]`) is for. It
supplies the plan or schema as Jinja context; your own template (and any
macros it imports from the same `searchpath`) decides what each output file
contains:

```python
from pathlib import Path
from ddldelta.render.jinja import JinjaRenderer
from ddldelta.sources import parse_path
from ddldelta.ddl_parser import parser_for

schema = parse_path(parser_for("mysql"), Path("ddl/current"))
renderer = JinjaRenderer(
    target_dir=Path("schemachange/acme/copy"),
    searchpath=Path("templates"),          # holds macros.sql.j2, copy_into.sql.j2
    template="copy_into.sql.j2",
    filename_template="A__copy_{{ table.name }}.sql",
)
renderer.render_schema(schema)
```

Unlike the migration renderers, `JinjaRenderer` *overwrites* its output on
every call rather than using the exists-guard — its files are regenerable
scaffolding, not checksummed migration history. Point it at a folder a
deploy tool also checksums (e.g. an `R__`/`A__` folder) only if you accept
that checksum discipline as your own responsibility, not the renderer's.

See [`examples/03_jinja_scaffolding.ipynb`](examples/03_jinja_scaffolding.ipynb)
for a full worked example that generates a set of per-table COPY INTO
scripts from a macro.

## Tests

```
uv run pytest tests
```

Run from the package directory. The test suite is pure and self-contained —
it imports only this package, pytest, and sqlglot; there is no dependency on
a consuming repository's fixtures, credentials, or file layout.

## Typing

The package ships a PEP 561 `py.typed` marker and is fully type-annotated —
every public function and method has parameter and return types. `mypy`
runs clean over `src/ddldelta`.
