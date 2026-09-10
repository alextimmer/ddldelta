import pytest

from ddldelta.ddl_parser import parser_for
from ddldelta.diff import schema_diff
from ddldelta.errors import GenerationError
from ddldelta.model import table_from
from ddldelta.sources import DeliveryDirectorySource, PathPairSource, rows_to_schema


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_lexikografisch_letzte_lieferung_gegen_vorgaenger(tmp_path):
    write(tmp_path / "2026Q2" / "a.sql", "CREATE TABLE a (id int)")
    write(tmp_path / "2026Q3" / "a.sql", "CREATE TABLE a (id int, neu int)")
    pair = DeliveryDirectorySource(tmp_path, parser_for("mysql")).load()
    assert (pair.old_label, pair.new_label) == ("2026Q2", "2026Q3")
    assert pair.comparison == "2026Q2 -> 2026Q3"
    assert [c.name for c in pair.new["a"].columns] == ["id", "neu"]


def test_erste_lieferung_hat_leeres_old(tmp_path):
    write(tmp_path / "2026Q3" / "a.sql", "CREATE TABLE a (id int)")
    pair = DeliveryDirectorySource(tmp_path, parser_for("mysql")).load()
    assert pair.old == {} and pair.old_label is None
    assert pair.comparison == "(initial) -> 2026Q3"


def test_ohne_lieferungen_none(tmp_path):
    assert DeliveryDirectorySource(tmp_path, parser_for("mysql")).load() is None


def test_unparsebare_ddl_nennt_datei(tmp_path):
    write(tmp_path / "2026Q3" / "kaputt.sql", "not ddl at all;;;")
    with pytest.raises(GenerationError, match="kaputt.sql"):
        DeliveryDirectorySource(tmp_path, parser_for("tsql")).load()


def test_fehlendes_wurzelverzeichnis_wirft_generation_error(tmp_path):
    with pytest.raises(GenerationError, match="fehlt-nicht-da"):
        DeliveryDirectorySource(tmp_path / "fehlt-nicht-da", parser_for("mysql")).load()


# ---- PathPairSource (explizite Zwei-Zustands-Quelle) ---------------------------

def test_zwei_verzeichnisse_ohne_namenskonvention(tmp_path):
    # Ordnernamen sortieren bewusst GEGEN die Chronologie - egal, der
    # Aufrufer bestimmt explizit, was alt und was neu ist.
    write(tmp_path / "z_alt" / "a.sql", "CREATE TABLE a (id int)")
    write(tmp_path / "a_neu" / "a.sql", "CREATE TABLE a (id int, neu int)")
    pair = PathPairSource(tmp_path / "z_alt", tmp_path / "a_neu",
                          parser_for("mysql")).load()
    assert (pair.old_label, pair.new_label) == ("z_alt", "a_neu")
    assert [c.name for c in pair.new["a"].columns] == ["id", "neu"]


def test_zwei_einzeldateien(tmp_path):
    write(tmp_path / "kunde_v1.sql", "CREATE TABLE kunde (id int)")
    write(tmp_path / "kunde_v2.sql", "CREATE TABLE kunde (id int, neu int)")
    pair = PathPairSource(tmp_path / "kunde_v1.sql", tmp_path / "kunde_v2.sql",
                          parser_for("mysql")).load()
    assert (pair.old_label, pair.new_label) == ("kunde_v1.sql", "kunde_v2.sql")
    assert list(pair.old) == ["kunde"] and list(pair.new) == ["kunde"]


def test_initial_ohne_old(tmp_path):
    write(tmp_path / "neu.sql", "CREATE TABLE kunde (id int)")
    pair = PathPairSource(None, tmp_path / "neu.sql", parser_for("mysql")).load()
    assert pair.old == {} and pair.old_label is None
    assert pair.comparison == "(initial) -> neu.sql"


def test_labels_ueberschreibbar(tmp_path):
    write(tmp_path / "x.sql", "CREATE TABLE kunde (id int)")
    pair = PathPairSource(None, tmp_path / "x.sql", parser_for("mysql"),
                          new_label="2026Q3").load()
    assert pair.comparison == "(initial) -> 2026Q3"


def test_fehlender_pfad_wirft_generation_error(tmp_path):
    with pytest.raises(GenerationError, match="gibts-nicht"):
        PathPairSource(None, tmp_path / "gibts-nicht.sql",
                       parser_for("mysql")).load()


def test_fehlender_old_pfad_wirft_generation_error(tmp_path):
    write(tmp_path / "neu.sql", "CREATE TABLE kunde (id int)")
    with pytest.raises(GenerationError, match="alt-gibts-nicht"):
        PathPairSource(tmp_path / "alt-gibts-nicht", tmp_path / "neu.sql",
                       parser_for("mysql")).load()


# ---- rows_to_schema (information_schema-Zeilen) ----------------------------

def test_rows_to_schema_gruppiert_verschachtelte_tabellen_in_reihenfolge():
    rows = [
        ("KUNDE", "id", "INT", True),
        ("KUNDE", "name", "VARCHAR", False),
        ("BESTELLUNG", "id", "INT", True),
        ("BESTELLUNG", "kunde_id", "INT", True),
    ]
    schema = rows_to_schema(rows)
    assert list(schema) == ["KUNDE", "BESTELLUNG"]
    assert [c.name for c in schema["KUNDE"].columns] == ["id", "name"]
    assert [c.name for c in schema["BESTELLUNG"].columns] == ["id", "kunde_id"]
    assert schema["KUNDE"].columns[1].type == "VARCHAR"
    assert schema["KUNDE"].columns[1].not_null is False
    assert schema["KUNDE"].key == ()


def test_rows_to_schema_diff_gegen_geparste_ddl_ist_leer():
    parsed = {"KUNDE": table_from("KUNDE", {"id": ("INT", True), "name": ("VARCHAR", False)})}
    rows = [("KUNDE", "id", "INT", True), ("KUNDE", "name", "VARCHAR", False)]
    schema = rows_to_schema(rows)
    assert schema_diff(parsed, schema) == {}


def test_rows_to_schema_nicht_konsekutive_tabelle_wirft_generation_error():
    # KUNDE-Zeilen sind durch eine BESTELLUNG-Zeile unterbrochen - groupby
    # wuerde das stillschweigend als zwei separate KUNDE-Gruppen behandeln
    # und die erste (name) verlieren, statt der Verletzung der
    # Vorordnungs-Voraussetzung zu widersprechen.
    rows = [
        ("KUNDE", "id", "INT", True),
        ("BESTELLUNG", "id", "INT", True),
        ("KUNDE", "name", "VARCHAR", False),
    ]
    with pytest.raises(GenerationError, match="KUNDE"):
        rows_to_schema(rows)
