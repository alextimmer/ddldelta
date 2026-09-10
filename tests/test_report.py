import json

from ddldelta.model import table_from
from ddldelta.policy import FusePolicy, Severity
from ddldelta.render.report import build_report


def test_kompatible_lieferung_exit_0():
    old = {"A": table_from("A", {"id": ("INT", True)})}
    new = {"A": table_from("A", {"id": ("INT", True), "neu": ("INT", False)})}
    report = build_report("n-1 -> n", old, new, FusePolicy())
    assert report.compatible is True
    assert report.exit_code == 0
    assert [f.severity for f in report.findings] == [Severity.SAFE]
    assert "n-1 -> n" in report.text()


def test_kritische_aenderung_exit_1_und_befundtext():
    old = {"A": table_from("A", {"id": ("INT", True), "weg": ("INT", False)})}
    new = {"A": table_from("A", {"id": ("VARCHAR", True)})}
    report = build_report("n-1 -> n", old, new, FusePolicy())
    assert report.compatible is False
    assert report.exit_code == 1
    assert len(report.critical) == 2
    text = report.text()
    assert '[critical] A: ALTER TABLE "A" DROP COLUMN "weg";' in text
    assert '[critical] A: ALTER TABLE "A" ALTER COLUMN "id" SET DATA TYPE VARCHAR;' in text


def test_keine_aenderung_exit_0_und_leermeldung():
    schema = {"A": table_from("A", {"id": ("INT", True)})}
    report = build_report("n-1 -> n", schema, schema, FusePolicy())
    assert report.findings == ()
    assert report.exit_code == 0
    assert report.text() == "n-1 -> n: no schema changes"


def test_create_table_befund_ist_einzeilig():
    new = {"A": table_from("A", {"id": ("INT", True), "b": ("VARCHAR", False)})}
    report = build_report("(initial) -> n", {}, new, FusePolicy())
    text = report.text()
    assert '[safe] A: CREATE TABLE "A" ( "id" INT NOT NULL, "b" VARCHAR );' in text
    assert len([l for l in text.splitlines() if l.startswith("  [")]) == len(report.findings)


# ---- to_json ----------------------------------------------------------------

def test_to_json_roundtrip_kritischer_befund():
    old = {"A": table_from("A", {"id": ("INT", True), "weg": ("INT", False)})}
    new = {"A": table_from("A", {"id": ("VARCHAR", True)})}
    report = build_report("n-1 -> n", old, new, FusePolicy())
    data = json.loads(report.to_json())
    assert data["comparison"] == "n-1 -> n"
    assert data["compatible"] is False
    assert data["exit_code"] == 1
    assert {f["severity"] for f in data["findings"]} == {"critical"}
    assert len(data["findings"]) == len(report.findings)
    assert {"table", "severity", "statement"} <= data["findings"][0].keys()


def test_to_json_leerer_befund():
    schema = {"A": table_from("A", {"id": ("INT", True)})}
    report = build_report("n-1 -> n", schema, schema, FusePolicy())
    data = json.loads(report.to_json())
    assert data["findings"] == []
    assert data["compatible"] is True


def test_to_json_sichere_aenderung_hat_severity_safe():
    old = {"A": table_from("A", {"id": ("INT", True)})}
    new = {"A": table_from("A", {"id": ("INT", True), "neu": ("INT", False)})}
    report = build_report("n-1 -> n", old, new, FusePolicy())
    data = json.loads(report.to_json())
    assert {f["severity"] for f in data["findings"]} == {"safe"}
