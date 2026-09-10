import json

import pytest

from ddldelta.ddl_parser import parser_for
from ddldelta.errors import GenerationError
from ddldelta.model import table_from
from ddldelta.snapshot import (
    SnapshotSource,
    load_snapshot,
    save_snapshot,
    schema_from_dict,
    schema_to_dict,
)


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_roundtrip_erhaelt_tabellen_key_und_label(tmp_path):
    schema = {"KUNDE": table_from("KUNDE", {"id": ("INT", True), "name": ("VARCHAR", False)},
                                   key=("id",))}
    path = tmp_path / "snapshot.json"
    save_snapshot(path, schema, "2026Q3")
    label, tables = load_snapshot(path)
    assert label == "2026Q3"
    assert tables == schema


def test_schema_to_dict_und_from_dict_sind_inverse():
    schema = {"KUNDE": table_from("KUNDE", {"id": ("INT", True)}, key=("id",))}
    data = schema_to_dict(schema, "2026Q3")
    assert data["ddldelta_snapshot"] == 1
    label, tables = schema_from_dict(data)
    assert (label, tables) == ("2026Q3", schema)


def test_save_snapshot_schreibt_lesbares_json_mit_trailing_newline(tmp_path):
    path = tmp_path / "sub" / "snapshot.json"
    save_snapshot(path, {"A": table_from("A", {"id": ("INT", True)})}, "2026Q3")
    text = path.read_text(encoding="utf-8")
    assert text.endswith("\n")
    assert json.loads(text)["label"] == "2026Q3"


def test_load_snapshot_fehlende_datei_wirft_generation_error_mit_pfad(tmp_path):
    path = tmp_path / "fehlt.json"
    with pytest.raises(GenerationError, match="fehlt.json"):
        load_snapshot(path)


def test_load_snapshot_ungueltiges_json_wirft_generation_error_mit_pfad(tmp_path):
    path = tmp_path / "kaputt.json"
    write(path, "{not json")
    with pytest.raises(GenerationError, match="kaputt.json"):
        load_snapshot(path)


def test_load_snapshot_fehlender_marker_wirft_generation_error(tmp_path):
    path = tmp_path / "ohne_marker.json"
    write(path, json.dumps({"label": "2026Q3", "tables": {}}))
    with pytest.raises(GenerationError, match="ohne_marker.json"):
        load_snapshot(path)


def test_schema_from_dict_unbekannte_version_wirft_generation_error():
    with pytest.raises(GenerationError, match="version"):
        schema_from_dict({"ddldelta_snapshot": 99, "label": "x", "tables": {}})


# ---- SnapshotSource --------------------------------------------------------

def test_snapshot_source_diffed_gegen_vorhandenen_snapshot(tmp_path):
    old_schema = {"A": table_from("A", {"id": ("INT", True)})}
    snapshot_path = tmp_path / "snapshot.json"
    save_snapshot(snapshot_path, old_schema, "2026Q2")
    write(tmp_path / "neu.sql", "CREATE TABLE a (id int, neu int)")

    pair = SnapshotSource(snapshot_path, tmp_path / "neu.sql", parser_for("mysql")).load()
    assert pair.old_label == "2026Q2"
    assert pair.old == old_schema
    assert [c.name for c in pair.new["a"].columns] == ["id", "neu"]
    assert pair.comparison == "2026Q2 -> neu.sql"


def test_snapshot_source_fehlender_snapshot_ist_initialzustand(tmp_path):
    write(tmp_path / "neu.sql", "CREATE TABLE a (id int)")
    pair = SnapshotSource(tmp_path / "fehlt.json", tmp_path / "neu.sql", parser_for("mysql")).load()
    assert pair.old == {} and pair.old_label is None
    assert pair.comparison == "(initial) -> neu.sql"


def test_snapshot_source_require_snapshot_fehlende_datei_wirft_generation_error(tmp_path):
    write(tmp_path / "neu.sql", "CREATE TABLE a (id int)")
    with pytest.raises(GenerationError, match="fehlt.json"):
        SnapshotSource(tmp_path / "fehlt.json", tmp_path / "neu.sql", parser_for("mysql"),
                       require_snapshot=True).load()


def test_snapshot_source_new_label_ueberschreibbar(tmp_path):
    write(tmp_path / "neu.sql", "CREATE TABLE a (id int)")
    pair = SnapshotSource(tmp_path / "fehlt.json", tmp_path / "neu.sql", parser_for("mysql"),
                          new_label="2026Q3").load()
    assert pair.comparison == "(initial) -> 2026Q3"


def test_workflow_schliesst_sich_naechster_lauf_sieht_gespeicherten_stand_als_alt(tmp_path):
    write(tmp_path / "delivery" / "a.sql", "CREATE TABLE a (id int)")
    snapshot_path = tmp_path / "snapshot.json"

    pair1 = SnapshotSource(snapshot_path, tmp_path / "delivery", parser_for("mysql"),
                           new_label="2026Q2").load()
    assert pair1.old == {}
    save_snapshot(snapshot_path, pair1.new, pair1.new_label)

    write(tmp_path / "delivery" / "a.sql", "CREATE TABLE a (id int, neu int)")
    pair2 = SnapshotSource(snapshot_path, tmp_path / "delivery", parser_for("mysql"),
                           new_label="2026Q3").load()
    assert pair2.old_label == "2026Q2"
    assert pair2.old == pair1.new
    assert [c.name for c in pair2.new["a"].columns] == ["id", "neu"]
