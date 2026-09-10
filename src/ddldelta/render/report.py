# Report-only mode: the schema-compatibility check as a value object with
# CI semantics (exit code 0/1), writing no files. "Is delivery n backward
# compatible with n-1?" - the fuse's severity model reused as a gate.

import json
from dataclasses import dataclass

from ddldelta.diff import schema_diff
from ddldelta.model import Schema
from ddldelta.policy import ChangePolicy, Severity
from ddldelta.render.sql import statement


@dataclass(frozen=True)
class Finding:
    table: str
    statement: str
    severity: Severity


@dataclass(frozen=True)
class CompatibilityReport:
    comparison: str
    findings: tuple[Finding, ...]

    @property
    def critical(self) -> tuple[Finding, ...]:
        return tuple(f for f in self.findings if f.severity is Severity.CRITICAL)

    @property
    def compatible(self) -> bool:
        return not self.critical

    @property
    def exit_code(self) -> int:
        return 0 if self.compatible else 1

    def text(self) -> str:
        if not self.findings:
            return f"{self.comparison}: no schema changes"
        lines = [f"{self.comparison}: {len(self.findings)} change(s), "
                 f"{len(self.critical)} critical"]
        lines += [
            f"  [{f.severity.value}] {f.table}: "
            + " ".join(part.strip() for part in f.statement.splitlines())
            for f in self.findings]
        return "\n".join(lines)

    def to_json(self) -> str:
        """CI-friendly JSON: comparison, compatible, exit_code, findings."""
        return json.dumps(
            {"comparison": self.comparison, "compatible": self.compatible,
             "exit_code": self.exit_code,
             "findings": [{"table": f.table, "severity": f.severity.value,
                            "statement": f.statement} for f in self.findings]},
            indent=2)


def build_report(comparison: str, old: Schema, new: Schema, policy: ChangePolicy) -> CompatibilityReport:
    findings = tuple(
        Finding(name, statement(change), policy.classify(change))
        for name, changes in schema_diff(old, new).items()
        for change in changes)
    return CompatibilityReport(comparison, findings)
