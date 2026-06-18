import sqlite3
from contextlib import contextmanager
from pathlib import Path

from .config import DB_FILE

SCHEMA = """
CREATE TABLE IF NOT EXISTS downloads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT NOT NULL,
    filename TEXT,
    out_dir TEXT NOT NULL,
    connections INTEGER NOT NULL DEFAULT 16,
    speed_limit_kbps INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'queued',
    gid TEXT,
    total_bytes INTEGER NOT NULL DEFAULT 0,
    completed_bytes INTEGER NOT NULL DEFAULT 0,
    error TEXT,
    created_at REAL NOT NULL,
    finished_at REAL,
    category TEXT NOT NULL DEFAULT 'Other',
    segments INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_downloads_status ON downloads(status);
CREATE INDEX IF NOT EXISTS idx_downloads_gid ON downloads(gid);
"""

_MIGRATIONS = [
    # v0 -> v1: add category and segments columns
    [
        "ALTER TABLE downloads ADD COLUMN category TEXT NOT NULL DEFAULT 'Other'",
        "ALTER TABLE downloads ADD COLUMN segments INTEGER NOT NULL DEFAULT 0",
    ],
    # v1 -> v2: add backend column for HLS support
    [
        "ALTER TABLE downloads ADD COLUMN backend TEXT DEFAULT 'aria2'",
    ],
]


def _migrate(conn: sqlite3.Connection) -> None:
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    for i, stmts in enumerate(_MIGRATIONS):
        if version <= i:
            for sql in stmts:
                try:
                    conn.execute(sql)
                except sqlite3.OperationalError as e:
                    if "duplicate column" not in str(e).lower():
                        raise
            conn.execute(f"PRAGMA user_version = {i + 1}")
    conn.commit()


def init(path: Path = DB_FILE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        conn.executescript(SCHEMA)
        _migrate(conn)


@contextmanager
def connect(path: Path = DB_FILE):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()
