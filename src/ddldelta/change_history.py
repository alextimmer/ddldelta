# The schemachange change-history convention: one table per project, named
# by a single rule, with the columns schemachange expects. Deploys never run
# with --create-change-history-table - the table is bootstrapped once by the
# consumer (chicken-and-egg: schemachange cannot create its own history
# table under our convention), so the structure lives here as the one place
# both the generated configs and the bootstrap draw from.


def change_history_table(project: str) -> str:
    """schemachange change-history table per project (unqualified name);
    the same convention is rendered into the generated configs."""
    return f"SCHEMACHANGE_CHANGE_HISTORY_{project.upper()}"


# Columns exactly as schemachange 4.3.3 would create them itself
# (schemachange/session/SnowflakeSession.py, create_change_history_table).
CHANGE_HISTORY_COLUMNS = """(
    VERSION VARCHAR,
    DESCRIPTION VARCHAR,
    SCRIPT VARCHAR,
    SCRIPT_TYPE VARCHAR,
    CHECKSUM VARCHAR,
    EXECUTION_TIME NUMBER,
    STATUS VARCHAR,
    INSTALLED_BY VARCHAR,
    INSTALLED_ON TIMESTAMP_LTZ
)"""
