import json
import sqlite3
from pathlib import Path
from typing import Any

from src.models.keys import Keys
import os
from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")

configured_db_path = os.getenv("DB_PATH")
if not configured_db_path:
    raise RuntimeError("DB_PATH is missing from the project .env file")
configured_db_path = Path(configured_db_path)
DB_PATH = str(
    configured_db_path / "keys.db"
    if configured_db_path.is_dir() or configured_db_path.suffix == ""
    else configured_db_path
)

_JSON_COLUMNS = {"rpmon", "rpm", "rpd", "tpd", "tpm", "tpmon"}
_UPDATE_COLUMNS = {
    "key_type", "api_url", "provider", "account_name", "api_key",
    "rpmon", "rpm", "rpd", "tpd", "tpm", "tpmon", "status",
}


def get_connection() -> sqlite3.Connection:
    """Open SQLite with rows accessible by column name."""
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def create_table() -> None:
    """Create the keys table if it does not exist."""
    with get_connection() as connection:
        existing = connection.execute("PRAGMA table_info(keys)").fetchall()
        if existing and existing[0]["type"].upper() == "INTEGER":
            row_count = connection.execute("SELECT COUNT(*) FROM keys").fetchone()[0]
            if row_count:
                raise RuntimeError(
                    "The existing keys table uses integer IDs; migrate its data before switching to UUIDs."
                )
            connection.execute("DROP TABLE keys")
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS keys (
                id TEXT PRIMARY KEY,
                key_type TEXT NOT NULL,
                api_url TEXT NOT NULL,
                provider TEXT NOT NULL,
                account_name TEXT NOT NULL,
                api_key TEXT NOT NULL,
                rpmon TEXT,
                rpm TEXT,
                rpd TEXT,
                tpd TEXT,
                tpm TEXT,
                tpmon TEXT,
                reg_date TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                status TEXT NOT NULL
            )
            """
        )
        columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(keys)")
        }
        for column in ("rpmon", "tpmon"):
            if column not in columns:
                connection.execute(f"ALTER TABLE keys ADD COLUMN {column} TEXT")


def clean_data(key: Keys | dict[str, Any]) -> dict[str, Any]:
    """Convert a key to database data and remove missing values."""
    if isinstance(key, Keys):
        data = key.model_dump(mode="json", exclude_none=True)
    else:
        data = {name: value for name, value in key.items() if value is not None}

    for column in _JSON_COLUMNS:
        if column in data:
            data[column] = json.dumps(data[column])

    data.pop("reg_date", None)
    return data


def insert_keys(keys: Keys | list[Keys]) -> list[str]:
    """Insert one key or many keys and return their database IDs."""
    if isinstance(keys, Keys):
        keys = [keys]
    if not keys:
        return []

    ids = []
    with get_connection() as connection:
        for key in keys:
            data = clean_data(key)
            columns = list(data)
            placeholders = ", ".join("?" for _ in columns)
            query = (
                f"INSERT INTO keys ({', '.join(columns)}) "
                f"VALUES ({placeholders})"
            )
            cursor = connection.execute(query, [data[column] for column in columns])
            ids.append(data["id"])
    return ids


def _decode_row(row: sqlite3.Row) -> dict[str, Any]:
    data = dict(row)
    for column in _JSON_COLUMNS:
        if data.get(column) is not None:
            data[column] = json.loads(data[column])
    return {name: value for name, value in data.items() if value is not None}


def row_to_key(row: sqlite3.Row) -> Keys:
    """Convert a database row into a Keys model without NULL fields."""
    data = _decode_row(row)
    data.pop("reg_date", None)
    return Keys.model_validate(data)


def get_key(key_id: str) -> Keys | None:
    """Return one key by ID, or None when it does not exist."""
    with get_connection() as connection:
        row = connection.execute(
            "SELECT * FROM keys WHERE id = ?", (key_id,)
        ).fetchone()
    return row_to_key(row) if row else None


def get_all_keys() -> list[Keys]:
    """Return all saved keys."""
    with get_connection() as connection:
        rows = connection.execute("SELECT * FROM keys ORDER BY id").fetchall()
    return [row_to_key(row) for row in rows]


def update_key(key_id: str, updates: dict[str, Any]) -> bool:
    """Update selected fields of one key."""
    data = clean_data(updates)
    data = {name: value for name, value in data.items() if name in _UPDATE_COLUMNS}
    if not data:
        return False

    assignments = ", ".join(f"{column} = ?" for column in data)
    values = [data[column] for column in data] + [key_id]
    with get_connection() as connection:
        cursor = connection.execute(
            f"UPDATE keys SET {assignments} WHERE id = ?", values
        )
    return cursor.rowcount > 0


def delete_keys(ids: str | list[str] | None = None) -> int:
    """Delete one key, many keys, or all keys; return count deleted."""
    with get_connection() as connection:
        if ids is None:
            cursor = connection.execute("DELETE FROM keys")
        else:
            if isinstance(ids, str):
                ids = [ids]
            if not ids:
                return 0
            placeholders = ", ".join("?" for _ in ids)
            cursor = connection.execute(
                f"DELETE FROM keys WHERE id IN ({placeholders})", ids
            )
    return cursor.rowcount


def health_check() -> bool:
    """Return True when SQLite can open and answer a query."""
    try:
        with get_connection() as connection:
            connection.execute("SELECT 1").fetchone()
        return True
    except sqlite3.Error:
        return False

def check_status():
    """Return True when SQLite can open and answer a query."""
    try:
        with get_connection() as connection:
            connection.execute("SELECT 1").fetchone()
        create_table()
        return True
    except sqlite3.Error:
        return False
