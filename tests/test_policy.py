from ddldelta.diff import (
    AddColumn,
    CreateTable,
    DropColumn,
    DropTable,
    NullabilityChange,
    TypeChange,
)
from ddldelta.model import Column, table_from
from ddldelta.policy import FusePolicy, Severity


def test_fuse_policy_klassifiziert_wie_heute():
    policy = FusePolicy()
    safe, critical = Severity.SAFE, Severity.CRITICAL
    assert policy.classify(CreateTable(table_from("A", {"id": ("INT", True)}))) is safe
    assert policy.classify(AddColumn("A", Column("c", "INT", False))) is safe
    assert policy.classify(AddColumn("A", Column("c", "INT", True))) is critical
    assert policy.classify(DropTable("A")) is critical
    assert policy.classify(DropColumn("A", "c")) is critical
    assert policy.classify(TypeChange("A", "c", "INT", "VARCHAR")) is critical
    assert policy.classify(NullabilityChange("A", "c", True)) is critical
    assert policy.classify(NullabilityChange("A", "c", False)) is critical


def test_eigene_policy_ist_nur_ein_protocol():
    class AllowEverything:
        def classify(self, change):
            return Severity.SAFE

    assert AllowEverything().classify(DropTable("A")) is Severity.SAFE
