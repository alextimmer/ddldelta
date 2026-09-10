from ddldelta.diff import (
    AddColumn,
    CreateTable,
    DropColumn,
    DropTable,
    NullabilityChange,
    TypeChange,
    schema_diff,
    table_diff,
)
from ddldelta.model import Column, table_from


def T(name, columns, key=()):
    return table_from(name, columns, key)


def test_neue_tabelle_ist_create():
    new = T("A", {"id": ("INT", True)})
    assert table_diff(None, new) == (CreateTable(new),)


def test_fehlende_tabelle_ist_drop():
    assert table_diff(T("A", {"id": ("INT", True)}), None) == (DropTable("A"),)


def test_identisch_ist_leer():
    a = T("A", {"id": ("INT", True)})
    assert table_diff(a, a) == ()
    assert schema_diff({"A": a}, {"A": a}) == {}
    assert table_diff(None, None) == ()


def test_reihenfolge_drops_zuerst_dann_neue_spalten_in_ddl_ordnung():
    old = T("A", {"weg": ("INT", False), "id": ("INT", True), "typ": ("INT", False)})
    new = T("A", {"id": ("INT", True), "typ": ("VARCHAR", True), "neu": ("INT", False)})
    assert table_diff(old, new) == (
        DropColumn("A", "weg"),
        TypeChange("A", "typ", "INT", "VARCHAR"),
        NullabilityChange("A", "typ", True),
        AddColumn("A", Column("neu", "INT", False)),
    )


def test_schema_diff_sortiert_tabellen_und_laesst_unveraenderte_weg():
    old = {"B": T("B", {"id": ("INT", True)}), "A": T("A", {"id": ("INT", True)})}
    new = {"B": T("B", {"id": ("INT", True)}),
           "C": T("C", {"id": ("INT", True)})}
    result = schema_diff(old, new)
    assert list(result) == ["A", "C"]          # sortiert; B unveraendert -> fehlt
    assert result["A"] == (DropTable("A"),)
    assert isinstance(result["C"][0], CreateTable)
