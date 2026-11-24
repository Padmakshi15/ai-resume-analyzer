"""Store each analysis so earlier and revised versions can be compared.

Two backends, chosen automatically:

* MySQL -- when the ``MYSQL_HOST`` environment variable is set.
  Connection settings come from ``MYSQL_HOST``, ``MYSQL_PORT``
  (default 3306), ``MYSQL_USER``, ``MYSQL_PASSWORD`` and
  ``MYSQL_DATABASE`` (default ``resume_analyzer``). The table is
  created automatically on first use.
* SQLite fallback -- otherwise. A local file ``data/analyses.db``
  is created next to this module, so the app runs anywhere with
  no database server. This is the default.

Both backends expose the same functions: ``save_analysis``,
``list_analyses``, ``get_analysis`` and ``compare_analyses``.
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_DB_PATH = Path(__file__).resolve().parent / "data" / "analyses.db"

MYSQL_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS analyses (
    id INT AUTO_INCREMENT PRIMARY KEY,
    created_at DATETIME NOT NULL,
    profile_name VARCHAR(255),
    match_percentage FLOAT NOT NULL,
    matched_skills JSON,
    missing_skills JSON,
    result JSON NOT NULL
)
"""

SQLITE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS analyses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    profile_name TEXT,
    match_percentage REAL NOT NULL,
    matched_skills TEXT,
    missing_skills TEXT,
    result TEXT NOT NULL
)
"""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _mysql_config() -> dict | None:
    host = os.getenv("MYSQL_HOST")
    if not host:
        return None
    return {
        "host": host,
        "port": int(os.getenv("MYSQL_PORT", "3306")),
        "user": os.getenv("MYSQL_USER", "root"),
        "password": os.getenv("MYSQL_PASSWORD", ""),
        "database": os.getenv("MYSQL_DATABASE", "resume_analyzer"),
    }


class SQLiteStore:
    """SQLite backend (default). One file, no server needed."""

    def __init__(self, db_path: str | os.PathLike | None = None) -> None:
        self.db_path = Path(db_path) if db_path else DEFAULT_DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(SQLITE_TABLE_SQL)

    def save_analysis(self, result: dict) -> int:
        profile = result.get("profile", {})
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO analyses "
                "(created_at, profile_name, match_percentage, "
                " matched_skills, missing_skills, result) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    _now_iso(),
                    profile.get("name", ""),
                    float(result.get("match_percentage", 0.0)),
                    json.dumps(result.get("matched_skills", [])),
                    json.dumps(result.get("missing_skills", [])),
                    json.dumps(result),
                ),
            )
            return int(cur.lastrowid)

    def list_analyses(self, limit: int = 20) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, created_at, profile_name, match_percentage, "
                "matched_skills, missing_skills FROM analyses "
                "ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [
            {
                "id": r["id"],
                "created_at": r["created_at"],
                "profile_name": r["profile_name"],
                "match_percentage": r["match_percentage"],
                "matched_skills": json.loads(r["matched_skills"] or "[]"),
                "missing_skills": json.loads(r["missing_skills"] or "[]"),
            }
            for r in rows
        ]

    def get_analysis(self, analysis_id: int) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT result FROM analyses WHERE id = ?", (analysis_id,)
            ).fetchone()
        return json.loads(row["result"]) if row else None


class MySQLStore:
    """MySQL backend, used when MYSQL_* environment variables are set."""

    def __init__(self, config: dict | None = None) -> None:
        self.config = config or _mysql_config()
        if not self.config:
            raise ValueError("MYSQL_HOST is not set - cannot use MySQLStore.")
        self._init_db()

    def _connect(self):
        try:
            import mysql.connector
        except ImportError as exc:  # pragma: no cover
            raise ImportError(
                "mysql-connector-python is required for MySQL storage. "
                "Install it with: pip install mysql-connector-python"
            ) from exc
        return mysql.connector.connect(**self.config)

    def _init_db(self) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(MYSQL_TABLE_SQL)
            conn.commit()

    def save_analysis(self, result: dict) -> int:
        profile = result.get("profile", {})
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO analyses "
                    "(created_at, profile_name, match_percentage, "
                    " matched_skills, missing_skills, result) "
                    "VALUES (%s, %s, %s, %s, %s, %s)",
                    (
                        datetime.now(timezone.utc).replace(tzinfo=None),
                        profile.get("name", ""),
                        float(result.get("match_percentage", 0.0)),
                        json.dumps(result.get("matched_skills", [])),
                        json.dumps(result.get("missing_skills", [])),
                        json.dumps(result),
                    ),
                )
                analysis_id = int(cur.lastrowid)
            conn.commit()
            return analysis_id

    def list_analyses(self, limit: int = 20) -> list[dict]:
        with self._connect() as conn:
            with conn.cursor(dictionary=True) as cur:
                cur.execute(
                    "SELECT id, created_at, profile_name, match_percentage, "
                    "matched_skills, missing_skills FROM analyses "
                    "ORDER BY id DESC LIMIT %s",
                    (limit,),
                )
                rows = cur.fetchall()
        out = []
        for r in rows:
            for key in ("matched_skills", "missing_skills"):
                if isinstance(r[key], str):
                    r[key] = json.loads(r[key] or "[]")
            r["created_at"] = str(r["created_at"])
            out.append(r)
        return out

    def get_analysis(self, analysis_id: int) -> dict | None:
        with self._connect() as conn:
            with conn.cursor(dictionary=True) as cur:
                cur.execute(
                    "SELECT result FROM analyses WHERE id = %s", (analysis_id,)
                )
                row = cur.fetchone()
        if not row:
            return None
        result = row["result"]
        return json.loads(result) if isinstance(result, str) else result


def get_store():
    """Return the MySQL store when MYSQL_HOST is set, else SQLite."""
    config = _mysql_config()
    if config:
        return MySQLStore(config)
    return SQLiteStore()


def compare_analyses(older: dict, newer: dict) -> dict:
    """Compare two stored analysis results (earlier vs revised resume).

    Returns newly matched skills, skills still missing, skills that
    are no longer missing, and the change in match percentage.
    """
    old_missing = set(older.get("missing_skills", []))
    new_missing = set(newer.get("missing_skills", []))
    old_matched = set(older.get("matched_skills", []))
    new_matched = set(newer.get("matched_skills", []))
    return {
        "newly_matched": sorted(new_matched - old_matched),
        "still_missing": sorted(new_missing),
        "no_longer_missing": sorted(old_missing - new_missing),
        "match_percentage_change": round(
            float(newer.get("match_percentage", 0.0))
            - float(older.get("match_percentage", 0.0)),
            1,
        ),
    }
