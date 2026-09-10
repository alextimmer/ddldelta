import pytest

jinja2 = pytest.importorskip("jinja2")

from ddldelta.errors import GenerationError
from ddldelta.model import table_from
from ddldelta.plan import build_plan
from ddldelta.policy import FusePolicy
from ddldelta.render.jinja import JinjaRenderer

MACROS = """\
{% macro migrate_header(label) %}-- deployed by pipeline {{ label }}{% endmacro %}
"""

MIGRATION_TEMPLATE = """\
{% import "macros.sql.j2" as macros %}
{{ macros.migrate_header(label) }}
{% for s in statements %}{{ s }}
{% endfor %}"""


def write_templates(tmp_path, **files):
    templates_dir = tmp_path / "templates"
    templates_dir.mkdir()
    for name, content in files.items():
        (templates_dir / name).write_text(content, encoding="utf-8")
    return templates_dir


def test_plan_gesteuertes_rendern_mit_makro(tmp_path):
    templates_dir = write_templates(
        tmp_path, **{"macros.sql.j2": MACROS, "migration.sql.j2": MIGRATION_TEMPLATE})
    new = {"NEU": table_from("NEU", {"id": ("INT", True)})}
    plan = build_plan("1", "(initial) -> 1", {}, new, FusePolicy())

    renderer = JinjaRenderer(
        target_dir=tmp_path / "out", searchpath=templates_dir,
        template="migration.sql.j2",
        filename_template="V{{ label }}__{{ table.table }}.sql")
    written = renderer.render(plan)

    target = tmp_path / "out" / "V1__NEU.sql"
    assert written == (target,)
    content = target.read_text(encoding="utf-8")
    assert "deployed by pipeline 1" in content
    assert 'CREATE TABLE "NEU"' in content


def test_kontext_ist_vollstaendig(tmp_path):
    templates_dir = write_templates(
        tmp_path,
        **{"ctx.sql.j2": "{{ label }} {{ comparison }} {{ critical }} {{ vars.env }}"})
    new = {"NEU": table_from("NEU", {"id": ("INT", True)})}
    plan = build_plan("1", "(initial) -> 1", {}, new, FusePolicy())

    renderer = JinjaRenderer(
        target_dir=tmp_path / "out", searchpath=templates_dir,
        template="ctx.sql.j2", filename_template="{{ table.table }}.sql",
        vars={"env": "dev"})
    renderer.render(plan)

    content = (tmp_path / "out" / "NEU.sql").read_text(encoding="utf-8")
    assert content == "1 (initial) -> 1 False dev"


def test_kritische_tabelle_liefert_rohe_statements(tmp_path):
    templates_dir = write_templates(
        tmp_path,
        **{"ctx.sql.j2": "critical={{ critical }}\n{% for s in statements %}{{ s }}\n{% endfor %}"})
    old = {"WEG": table_from("WEG", {"id": ("INT", True)})}
    plan = build_plan("1", "0 -> 1", old, {}, FusePolicy())

    renderer = JinjaRenderer(
        target_dir=tmp_path / "out", searchpath=templates_dir,
        template="ctx.sql.j2", filename_template="{{ table.table }}.sql")
    renderer.render(plan)

    content = (tmp_path / "out" / "WEG.sql").read_text(encoding="utf-8")
    assert "critical=True" in content
    assert 'DROP TABLE "WEG";' in content
    assert "-- DROP TABLE" not in content


COPY_MACROS = """\
{% macro copy_into(table, columns) %}COPY INTO {{ table }} ({{ columns | join(', ') }}) ...{% endmacro %}
"""

COPY_TEMPLATE = """\
{% import "copy_macros.sql.j2" as macros %}
{{ macros.copy_into(table.name, columns) }}
"""


def test_schema_gesteuertes_scaffolding(tmp_path):
    templates_dir = write_templates(
        tmp_path, **{"copy_macros.sql.j2": COPY_MACROS, "copy_into.sql.j2": COPY_TEMPLATE})
    schema = {
        "KUNDE": table_from("KUNDE", {"id": ("INT", True), "name": ("VARCHAR", False)}),
    }

    renderer = JinjaRenderer(
        target_dir=tmp_path / "out", searchpath=templates_dir,
        template="copy_into.sql.j2",
        filename_template="A__copy_{{ table.name }}.sql")
    written = renderer.render_schema(schema, label="2026Q3")

    assert written == (tmp_path / "out" / "A__copy_KUNDE.sql",)
    content = written[0].read_text(encoding="utf-8")
    assert "id, name" in content


def test_ueberschreiben_ohne_exists_guard(tmp_path):
    templates_dir = write_templates(tmp_path, **{"t.sql.j2": "{{ vars.value }}"})
    schema = {"NEU": table_from("NEU", {"id": ("INT", True)})}
    renderer = JinjaRenderer(
        target_dir=tmp_path / "out", searchpath=templates_dir,
        template="t.sql.j2", filename_template="{{ table.name }}.sql",
        vars={"value": "erst"})
    renderer.render_schema(schema)

    renderer2 = JinjaRenderer(
        target_dir=tmp_path / "out", searchpath=templates_dir,
        template="t.sql.j2", filename_template="{{ table.name }}.sql",
        vars={"value": "zweitens"})
    renderer2.render_schema(schema)

    content = (tmp_path / "out" / "NEU.sql").read_text(encoding="utf-8")
    assert content == "zweitens"


def test_fehlende_variable_scheitert_laut(tmp_path):
    templates_dir = write_templates(tmp_path, **{"broken.sql.j2": "{{ nope }}"})
    new = {"NEU": table_from("NEU", {"id": ("INT", True)})}
    plan = build_plan("1", "(initial) -> 1", {}, new, FusePolicy())

    renderer = JinjaRenderer(
        target_dir=tmp_path / "out", searchpath=templates_dir,
        template="broken.sql.j2", filename_template="{{ table.table }}.sql")

    with pytest.raises(GenerationError, match="broken.sql.j2"):
        renderer.render(plan)


def test_dateiname_ausserhalb_target_dir_scheitert(tmp_path):
    templates_dir = write_templates(tmp_path, **{"t.sql.j2": "x"})
    schema = {"NEU": table_from("NEU", {"id": ("INT", True)})}
    renderer = JinjaRenderer(
        target_dir=tmp_path / "out", searchpath=templates_dir,
        template="t.sql.j2", filename_template="../../escaped_{{ table.name }}.sql")

    with pytest.raises(GenerationError, match="escapes"):
        renderer.render_schema(schema)


def test_boesartiger_tabellenname_scheitert(tmp_path):
    templates_dir = write_templates(tmp_path, **{"t.sql.j2": "x"})
    schema = {"../evil": table_from("../evil", {"id": ("INT", True)})}
    renderer = JinjaRenderer(
        target_dir=tmp_path / "out", searchpath=templates_dir,
        template="t.sql.j2", filename_template="{{ table.name }}.sql")

    with pytest.raises(GenerationError, match="escapes"):
        renderer.render_schema(schema)


def test_leerer_dateiname_scheitert(tmp_path):
    templates_dir = write_templates(tmp_path, **{"t.sql.j2": "x"})
    schema = {"NEU": table_from("NEU", {"id": ("INT", True)})}
    renderer = JinjaRenderer(
        target_dir=tmp_path / "out", searchpath=templates_dir,
        template="t.sql.j2", filename_template="   ")

    with pytest.raises(GenerationError, match="empty file name"):
        renderer.render_schema(schema)


def test_harmloser_unterordner_wird_angelegt(tmp_path):
    templates_dir = write_templates(tmp_path, **{"t.sql.j2": "{{ table.name }}"})
    schema = {"NEU": table_from("NEU", {"id": ("INT", True)})}
    renderer = JinjaRenderer(
        target_dir=tmp_path / "out", searchpath=templates_dir,
        template="t.sql.j2", filename_template="sub/{{ table.name }}.sql")

    written = renderer.render_schema(schema)

    target = tmp_path / "out" / "sub" / "NEU.sql"
    assert written == (target,)
    assert target.read_text(encoding="utf-8") == "NEU"


def test_dateisystemfehler_wird_verstaendlich_verpackt(tmp_path):
    # target_dir's path is occupied by a plain FILE, not a directory, so
    # mkdir(parents=True, exist_ok=True) raises FileExistsError (an OSError)
    # when _write tries to create it - exercising the OSError -> GenerationError wrap.
    templates_dir = write_templates(tmp_path, **{"t.sql.j2": "{{ table.name }}"})
    target_dir = tmp_path / "out"
    target_dir.write_text("occupied by a file, not a directory", encoding="utf-8")
    schema = {"NEU": table_from("NEU", {"id": ("INT", True)})}
    renderer = JinjaRenderer(
        target_dir=target_dir, searchpath=templates_dir,
        template="t.sql.j2", filename_template="{{ table.name }}.sql")

    with pytest.raises(GenerationError, match="cannot write"):
        renderer.render_schema(schema)


def test_fehlt_jinja2_liefert_verstaendlichen_fehler(tmp_path, monkeypatch):
    import ddldelta.render.jinja as jinja_module

    def boom():
        raise ImportError("no jinja2")

    monkeypatch.setattr(jinja_module, "_import_jinja2", boom)

    new = {"NEU": table_from("NEU", {"id": ("INT", True)})}
    plan = build_plan("1", "(initial) -> 1", {}, new, FusePolicy())
    renderer = JinjaRenderer(
        target_dir=tmp_path / "out", searchpath=tmp_path,
        template="whatever.sql.j2", filename_template="{{ table.table }}.sql")

    with pytest.raises(GenerationError, match=r"ddldelta\[jinja\]"):
        renderer.render(plan)
