from ddldelta.change_history import (
    CHANGE_HISTORY_COLUMNS, change_history_table)


def test_namenskonvention_je_projekt():
    assert change_history_table("haynespro") == "SCHEMACHANGE_CHANGE_HISTORY_HAYNESPRO"
    assert change_history_table("metadata") == "SCHEMACHANGE_CHANGE_HISTORY_METADATA"


def test_spalten_entsprechen_schemachange():
    # Der Spaltensatz, den schemachange 4.3.3 selbst anlegen wuerde - die
    # Bootstrap-DDL muss ihn exakt treffen, sonst scheitern Deploys.
    for column in ("VERSION", "DESCRIPTION", "SCRIPT", "SCRIPT_TYPE", "CHECKSUM",
                   "EXECUTION_TIME", "STATUS", "INSTALLED_BY", "INSTALLED_ON"):
        assert column in CHANGE_HISTORY_COLUMNS
    assert CHANGE_HISTORY_COLUMNS.startswith("(")
    assert CHANGE_HISTORY_COLUMNS.endswith(")")
