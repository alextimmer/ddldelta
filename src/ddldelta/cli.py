# Command-line entry point. Thin wrapper over the library: the only module
# in the package allowed to print or exit - the core (plan.py, render/*,
# sources.py, ...) stays log-free and never exits (see CLAUDE.md). Import-
# side-effect-free like the host repo's pipeline modules (argparse built
# inside functions, `main(argv) -> int` pattern) so tests can call `main`
# in-process without a subprocess.
#
# Deliberately NOT exposed here: meta_ddl / provenance-template / custom
# ChangePolicy injection, and generate_supplier's schemachange-config.yml
# orchestration - those stay library-only (GeneratorConfig), see the
# README's "Command line" section.

import argparse
import sys
from collections.abc import Callable
from pathlib import Path

from ddldelta.ddl_parser import ParseResult, parser_for
from ddldelta.errors import GenerationError
from ddldelta.model import Table
from ddldelta.plan import MigrationPlan, Renderer, baseline_plan, build_plan
from ddldelta.policy import FusePolicy
from ddldelta.render.flyway import FlywayRenderer
from ddldelta.render.report import build_report
from ddldelta.render.schemachange import SchemachangeRenderer
from ddldelta.snapshot import load_snapshot, save_snapshot
from ddldelta.sources import parse_path

_EPILOG = (
    "Advanced knobs - meta columns, a custom provenance template, a custom "
    "ChangePolicy, or the generate_supplier/GeneratorConfig orchestration "
    "(schemachange-config.yml) - are library-level only; use ddldelta as a "
    "Python package for those. See the README.")

# Every schema-state argument (OLD/NEW/--old) accepts the same three forms.
_STATE_HELP = "a directory of *.sql files, a single .sql file, or a .json ddldelta snapshot."

# I2: PK/grain changes are parsed and snapshotted (Table.key) but never
# diffed - schema_diff compares columns only. Deliberate, not an oversight:
# keys were never part of generated DDL, and diffing them would retroactively
# re-fuse every past delivery that only ever changed a primary key, breaking
# the regeneration-is-a-no-op guarantee. See README "What it is not" / roadmap.
_CHECK_EPILOG = (
    "Note: primary-key changes are parsed and snapshotted but NOT diffed - "
    "a PK/grain change passes this check silently today. See the README.")


def _load_state(path: Path, parse_ddl: Callable[[str], ParseResult]) -> tuple[str | None, dict[str, Table]]:
    """One schema-state argument -> (label, schema). A `.json` suffix is
    read as a ddldelta snapshot (stored label wins); anything else is
    parsed as DDL (a directory of *.sql or a single .sql file), labelled by
    the path's own name."""
    if path.suffix == ".json":
        return load_snapshot(path)
    return path.name, parse_path(parse_ddl, path)


def _renderer(args: argparse.Namespace) -> Renderer:
    cls = FlywayRenderer if args.flyway else SchemachangeRenderer
    return cls(target_dir=args.out, generated_by=args.generated_by)


def _print_written(written: tuple[Path, ...]) -> None:
    for path in written:
        print(path)


def _warn_critical(plan: MigrationPlan) -> None:
    """M9: a fused table is not a CLI error (the fuse - SELECT 1/0 - is
    schemachange's/Flyway's deploy-time gate, not this command's); but a
    silent 0 exit next to fused files is easy to miss in a script, so flag
    it on stderr without changing the exit code."""
    if plan.critical_tables:
        print(f"{len(plan.critical_tables)} critical table(s) fused - review required",
              file=sys.stderr)


def _check(args: argparse.Namespace, parse_ddl: Callable[[str], ParseResult]) -> int:
    old_label, old = _load_state(args.old, parse_ddl)
    new_label, new = _load_state(args.new, parse_ddl)
    comparison = f"{old_label or '(initial)'} -> {new_label}"
    report = build_report(comparison, old, new, FusePolicy())
    print(report.to_json() if args.json else report.text())
    return report.exit_code


def _generate(args: argparse.Namespace, parse_ddl: Callable[[str], ParseResult]) -> int:
    old_label, old = _load_state(args.old, parse_ddl) if args.old is not None else (None, {})
    _, new = _load_state(args.new, parse_ddl)
    comparison = f"{old_label or '(initial)'} -> {args.label}"
    plan: MigrationPlan = build_plan(args.label, comparison, old, new, FusePolicy())
    written = _renderer(args).render(plan)
    _print_written(written)
    _warn_critical(plan)
    if args.snapshot is not None:
        save_snapshot(args.snapshot, new, args.label)
        print(args.snapshot)
    return 0


def _baseline(args: argparse.Namespace, parse_ddl: Callable[[str], ParseResult]) -> int:
    _, new = _load_state(args.new, parse_ddl)
    plan = baseline_plan(args.label, new)
    _print_written(_renderer(args).render(plan))
    _warn_critical(plan)   # baseline can never be critical (CreateTable is SAFE) - kept for symmetry
    return 0


def _snapshot(args: argparse.Namespace, parse_ddl: Callable[[str], ParseResult]) -> int:
    _, new = _load_state(args.new, parse_ddl)
    save_snapshot(args.out, new, args.label)
    print(args.out)
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ddldelta",
        description="Offline DDL-diff migration-plan generator "
                    "(schemachange, Flyway, CI compatibility report).",
        epilog=_EPILOG)
    subparsers = parser.add_subparsers(dest="command", required=True)

    check = subparsers.add_parser(
        "check", help="Compatibility check between two schema states (CI gate).",
        epilog=_CHECK_EPILOG)
    check.add_argument("--dialect", required=True, help="sqlglot dialect name, e.g. mysql, tsql.")
    check.add_argument("old", type=Path, help=f"Old schema state: {_STATE_HELP}")
    check.add_argument("new", type=Path, help=f"New schema state: {_STATE_HELP}")
    check.add_argument("--json", action="store_true",
                       help="Print the report as JSON instead of text.")

    generate = subparsers.add_parser(
        "generate", help="Render versioned migration files for the diff between two schema states.")
    generate.add_argument("--dialect", required=True, help="sqlglot dialect name, e.g. mysql, tsql.")
    generate.add_argument("--label", required=True,
                          help="Version label for the new state (e.g. a delivery name).")
    generate.add_argument("--out", required=True, type=Path,
                          help="Target directory for the generated migration files.")
    generate.add_argument("new", type=Path, help=f"New schema state: {_STATE_HELP}")
    generate.add_argument("--old", type=Path, default=None,
                          help=f"Old schema state: {_STATE_HELP} Omit for an initial "
                               "migration (every table is new).")
    generate.add_argument("--generated-by", dest="generated_by", default="ddldelta",
                          help="Provenance tag written into the generated files (default: ddldelta).")
    generate.add_argument("--flyway", action="store_true",
                          help="Render Flyway-style files instead of schemachange "
                               "(requires a numeric --label).")
    generate.add_argument("--snapshot", type=Path, default=None,
                          help="After a successful render, save the new state here as a "
                               "ddldelta snapshot for the next run's --old.")

    baseline = subparsers.add_parser(
        "baseline", help="Render the current state as a fresh CREATE-only migration set.")
    baseline.add_argument("--dialect", required=True, help="sqlglot dialect name, e.g. mysql, tsql.")
    baseline.add_argument("--label", required=True, help="Version label for the baseline.")
    baseline.add_argument("--out", required=True, type=Path,
                          help="Target directory for the generated migration files.")
    baseline.add_argument("new", type=Path, help=f"Schema state to baseline: {_STATE_HELP}")
    baseline.add_argument("--generated-by", dest="generated_by", default="ddldelta",
                          help="Provenance tag written into the generated files (default: ddldelta).")
    baseline.add_argument("--flyway", action="store_true",
                          help="Render Flyway-style files instead of schemachange "
                               "(requires a numeric --label).")

    snapshot = subparsers.add_parser(
        "snapshot", help="Save a schema state as a ddldelta snapshot for a later run's --old.")
    snapshot.add_argument("--dialect", required=True, help="sqlglot dialect name, e.g. mysql, tsql.")
    snapshot.add_argument("--label", required=True, help="Label stored in the snapshot.")
    snapshot.add_argument("--out", required=True, type=Path, help="Snapshot file to write.")
    snapshot.add_argument("new", type=Path, help=f"Schema state to snapshot: {_STATE_HELP}")

    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        parse_ddl = parser_for(args.dialect)
        if args.command == "check":
            return _check(args, parse_ddl)
        if args.command == "generate":
            return _generate(args, parse_ddl)
        if args.command == "baseline":
            return _baseline(args, parse_ddl)
        if args.command == "snapshot":
            return _snapshot(args, parse_ddl)
        raise AssertionError(f"unhandled command: {args.command!r}")
    except (GenerationError, ValueError, OSError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    except Exception as error:   # noqa: BLE001 - last resort: a crash must
        # never fall through to rc 1, the "check found critical findings"
        # code - that would falsify a CI gate reading the exit code alone.
        print(f"error: unexpected: {error!r}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
