from ddldelta.model import table_from
from ddldelta.plan import build_plan
from ddldelta.policy import FusePolicy
from ddldelta.render.schemachange import SchemachangeRenderer

META = ('"_DELIVERY" VARCHAR',)
GERMAN = "-- generiert von {generated_by} ({comparison}); nicht manuell aendern"


def render(tmp_path, old, new, label="2026Q3", comparison="2026Q2 -> 2026Q3"):
    plan = build_plan(label, comparison, old, new, FusePolicy())
    renderer = SchemachangeRenderer(
        target_dir=tmp_path, generated_by="test.generator", meta_ddl=META,
        provenance_template=GERMAN)
    return renderer.render(plan)


def test_dateinamen_zaehler_und_fuse(tmp_path):
    old = {"WEG": table_from("WEG", {"id": ("INT", True)})}
    new = {"NEU": table_from("NEU", {"id": ("INT", True)})}
    written = render(tmp_path, old, new)
    assert [p.name for p in written] == [
        "V2026Q3.0001__NEU.sql", "V2026Q3.0002__WEG.sql",
        "V2026Q3.0000__CRITICAL_CHANGES.sql"]
    weg = (tmp_path / "V2026Q3.0002__WEG.sql").read_text(encoding="utf-8")
    assert weg == (
        "-- generiert von test.generator (2026Q2 -> 2026Q3); nicht manuell aendern\n"
        'SELECT 1/0 AS "CRITICAL CHANGES DETECTED - PLEASE REVIEW THIS FILE!";\n'
        '-- DROP TABLE "WEG";\n')
    summary = (tmp_path / "V2026Q3.0000__CRITICAL_CHANGES.sql").read_text(encoding="utf-8")
    assert "-- V2026Q3.0002__WEG.sql" in summary
    neu = (tmp_path / "V2026Q3.0001__NEU.sql").read_text(encoding="utf-8")
    assert neu == (
        "-- generiert von test.generator (2026Q2 -> 2026Q3); nicht manuell aendern\n"
        'CREATE TABLE "NEU" (\n'
        '    "id" INT NOT NULL,\n'
        '    "_DELIVERY" VARCHAR\n'
        ");\n")


def test_rerun_ist_noop(tmp_path):
    new = {"NEU": table_from("NEU", {"id": ("INT", True)})}
    assert len(render(tmp_path, {}, new)) == 1
    assert render(tmp_path, {}, new) == ()      # exists-guard: identisch -> skip
