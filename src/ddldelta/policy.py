# Classifies typed changes. CRITICAL means: statements are emitted only as
# comments behind a SELECT 1/0 fuse - the deploy fails on purpose until a
# human reviewed the change. The old enforce_not_null=False mode is NOT a
# policy concern: it is model normalization (model.without_nullability),
# after which nullability changes simply do not exist.

from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from ddldelta.diff import (
    AddColumn,
    Change,
    CreateTable,
    DropColumn,
    DropTable,
    NullabilityChange,
    TypeChange,
)


class Severity(Enum):
    SAFE = "safe"
    CRITICAL = "critical"


class ChangePolicy(Protocol):
    def classify(self, change: Change) -> Severity: ...


@dataclass(frozen=True)
class FusePolicy:
    """Default policy: anything destructive or lossy is critical."""

    def classify(self, change: Change) -> Severity:
        match change:
            case CreateTable():
                return Severity.SAFE
            case AddColumn(column=column):
                return Severity.CRITICAL if column.not_null else Severity.SAFE
            case DropTable() | DropColumn() | TypeChange() | NullabilityChange():
                return Severity.CRITICAL
        raise TypeError(f"unknown change type: {change!r}")
