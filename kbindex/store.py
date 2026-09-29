from pathlib import Path

from psycopg import ClientCursor


def apply_schema(connection):
    """Create the four knowledge-base tables when they are missing."""
    with ClientCursor(connection) as cursor:
        cursor.execute(Path(__file__).with_name("schema.sql").read_text())
    connection.commit()
