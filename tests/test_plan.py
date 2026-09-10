from ddldelta.model import table_from
from ddldelta.plan import baseline_plan, build_plan
from ddldelta.policy import FusePolicy
from ddldelta.render.schemachange import SchemachangeRenderer


def test_build_plan_buendelt_diff_und_policy():
    old = {"WEG": table_from("WEG", {"id": ("INT", True)}),
           "OK": table_from("OK", {"id": ("INT", True)})}
    new = {"OK": table_from("OK", {"id": ("INT", True), "neu": ("INT", False)}),
           "NEU": table_from("NEU", {"id": ("INT", True)})}
    plan = build_plan("2026Q3", "2026Q2 -> 2026Q3", old, new, FusePolicy())
    assert plan.label == "2026Q3"
    assert plan.comparison == "2026Q2 -> 2026Q3"
    assert [(t.table, t.critical) for t in plan.tables] == [
        ("NEU", False), ("OK", False), ("WEG", True)]
    assert [t.table for t in plan.critical_tables] == ["WEG"]


# ---- baseline_plan ---------------------------------------------------------

def test_baseline_plan_erzeugt_nur_create_tables_und_ist_unkritisch():
    schema = {"A": table_from("A", {"id": ("INT", True)}),
              "B": table_from("B", {"id": ("INT", True), "n": ("VARCHAR", False)})}
    plan = baseline_plan("2026Q3", schema)
    assert plan.label == "2026Q3"
    assert plan.comparison == "(baseline) -> 2026Q3"
    assert len(plan.tables) == 2
    assert all(not t.critical for t in plan.tables)
    assert all(len(t.changes) == 1 for t in plan.tables)
    assert all(type(t.changes[0]).__name__ == "CreateTable" for t in plan.tables)
    assert plan.critical_tables == ()


def test_baseline_plan_comparison_ueberschreibbar():
    schema = {"A": table_from("A", {"id": ("INT", True)})}
    plan = baseline_plan("2026Q3", schema, comparison="re-baseline 2026Q3")
    assert plan.comparison == "re-baseline 2026Q3"


def test_baseline_plan_rendert_ausfuehrbare_create_dateien(tmp_path):
    schema = {"A": table_from("A", {"id": ("INT", True)}),
              "B": table_from("B", {"id": ("INT", True)})}
    plan = baseline_plan("2026Q3", schema)
    renderer = SchemachangeRenderer(target_dir=tmp_path, generated_by="test.generator")
    written = renderer.render(plan)
    assert len(written) == 2
    for path in written:
        text = path.read_text(encoding="utf-8")
        assert "CREATE TABLE" in text
        assert "SELECT 1/0" not in text
