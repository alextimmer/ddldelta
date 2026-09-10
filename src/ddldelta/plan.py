# Bundles diff + policy verdicts into the unit renderers consume. A table
# is critical as soon as ONE of its changes is - matching the fuse
# semantics: the whole file becomes comments behind SELECT 1/0.

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from ddldelta.diff import Change, schema_diff
from ddldelta.model import Schema
from ddldelta.policy import ChangePolicy, FusePolicy, Severity


@dataclass(frozen=True)
class TablePlan:
    table: str
    changes: tuple[Change, ...]
    critical: bool


@dataclass(frozen=True)
class MigrationPlan:
    label: str          # version label of the new state (e.g. delivery name)
    comparison: str     # "<old|(initial)> -> <new>"
    tables: tuple[TablePlan, ...]

    @property
    def critical_tables(self) -> tuple[TablePlan, ...]:
        return tuple(t for t in self.tables if t.critical)


class Renderer(Protocol):
    def render(self, plan: MigrationPlan) -> tuple[Path, ...]: ...


def build_plan(label: str, comparison: str, old: Schema, new: Schema,
               policy: ChangePolicy) -> MigrationPlan:
    tables = tuple(
        TablePlan(name, changes,
                  any(policy.classify(c) is Severity.CRITICAL for c in changes))
        for name, changes in schema_diff(old, new).items())
    return MigrationPlan(label, comparison, tables)


def baseline_plan(label: str, schema: Schema,
                  policy: ChangePolicy | None = None,
                  comparison: str | None = None) -> MigrationPlan:
    """The current state as a fresh CREATE set - a baseline for new
    environments (pairs with Flyway baseline / schemachange re-baselining).
    Equivalent to diffing an empty schema against the current one."""
    return build_plan(label, comparison or f"(baseline) -> {label}",
                      {}, schema, policy or FusePolicy())
