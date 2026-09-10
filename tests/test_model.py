from ddldelta.model import Column, Table, table_from, without_nullability


def test_table_from_erhaelt_spaltenreihenfolge_und_key():
    table = table_from("T", {"b": ("INT", True), "a": ("VARCHAR", False)}, key=("b",))
    assert table.columns == (Column("b", "INT", True), Column("a", "VARCHAR", False))
    assert table.key == ("b",)
    assert table.columns_by_name == {"b": Column("b", "INT", True),
                                     "a": Column("a", "VARCHAR", False)}


def test_without_nullability_setzt_alle_spalten_nullable():
    schema = {"T": table_from("T", {"a": ("INT", True), "b": ("INT", False)})}
    stripped = without_nullability(schema)
    assert all(not c.not_null for c in stripped["T"].columns)
    # Original bleibt unangetastet (frozen)
    assert schema["T"].columns[0].not_null is True
