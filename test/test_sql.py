
import sqlite3

def get_connection() -> sqlite3.Connection:
    """Open SQLite with rows accessible by column name."""
    connection = sqlite3.connect("./keys.db")
    connection.row_factory = sqlite3.Row
    return connection


def check_status():
    """Return True when SQLite can open and answer a query."""
    try:
        with get_connection() as connection:
            con = connection.execute("SELECT 1").fetchone()
            print(con)
        return True
    except sqlite3.Error:
        return False


if __name__ == "__main__":
    status = check_status()
    print(f"SQLite status: {status}")