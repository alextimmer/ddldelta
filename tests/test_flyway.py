import pytest

from ddldelta.errors import GenerationError
from ddldelta.model import table_from
from ddldelta.plan import build_plan
from ddldelta.policy import FusePolicy
from ddldelta.render.flyway import FlywayRenderer


def plan_for(label="3.46.2"):
    return build_plan(label, f"(initial) -> {label}",
                      {}, {"NEU": table_from("NEU", {"id": ("INT", True)})},
                      FusePolicy())


def test_schreibt_flyway_konforme_versionsdateien(tmp_path):
    written = FlywayRenderer(target_dir=tmp_path, generated_by="test").render(plan_for())
    assert [p.name for p in written] == ["V3.46.2.0001__NEU.sql"]
    content = written[0].read_text(encoding="utf-8")
    assert content.splitlines()[0].startswith("-- ")     # Provenienz
    assert 'CREATE TABLE "NEU"' in content


def test_ungueltiges_flyway_label_bricht_ab(tmp_path):
    with pytest.raises(GenerationError, match="2026Q3"):
        FlywayRenderer(target_dir=tmp_path, generated_by="test").render(plan_for("2026Q3"))


def test_kritische_tabelle_bekommt_fuse_und_summary(tmp_path):
    old = {"WEG": table_from("WEG", {"id": ("INT", True)})}
    plan = build_plan("3.46.2", "3.46.1 -> 3.46.2", old, {}, FusePolicy())
    written = FlywayRenderer(target_dir=tmp_path, generated_by="test").render(plan)
    assert [p.name for p in written] == [
        "V3.46.2.0001__WEG.sql", "V3.46.2.0000__CRITICAL_CHANGES.sql"]
    weg = (tmp_path / "V3.46.2.0001__WEG.sql").read_text(encoding="utf-8")
    assert 'SELECT 1/0 AS "CRITICAL CHANGES DETECTED - PLEASE REVIEW THIS FILE!";' in weg
    assert '-- DROP TABLE "WEG";' in weg
    summary = (tmp_path / "V3.46.2.0000__CRITICAL_CHANGES.sql").read_text(encoding="utf-8")
    assert "-- V3.46.2.0001__WEG.sql" in summary
