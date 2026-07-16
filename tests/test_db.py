"""Tests for additive cove.db migrations."""

import sqlite3
import time

from cove import db


def _v0_db(path):
    """Create a pre-migration (v0) database with one legacy row."""
    conn = sqlite3.connect(path)
    conn.executescript(db.SCHEMA)
    conn.execute(
        "INSERT INTO downloads (url, out_dir, created_at) VALUES (?,?,?)",
        ("https://example.com/f.zip", "/dl", time.time()),
    )
    conn.commit()
    conn.close()


def test_old_db_gains_convert_mp3_default_zero(tmp_path):
    path = tmp_path / "cove.db"
    _v0_db(path)
    db.init(path)
    with db.connect(path) as conn:
        row = conn.execute("SELECT * FROM downloads").fetchone()
        assert row["convert_mp3"] == 0
        version = conn.execute("PRAGMA user_version").fetchone()[0]
    assert version == len(db._MIGRATIONS)


def test_init_idempotent(tmp_path):
    path = tmp_path / "cove.db"
    db.init(path)
    db.init(path)
    with db.connect(path) as conn:
        cols = [r["name"] for r in conn.execute("PRAGMA table_info(downloads)")]
    assert "convert_mp3" in cols


def test_convert_mp3_round_trips(tmp_path):
    path = tmp_path / "cove.db"
    db.init(path)
    with db.connect(path) as conn:
        conn.execute(
            "INSERT INTO downloads (url, out_dir, created_at, convert_mp3) "
            "VALUES (?,?,?,?)",
            ("https://example.com/a.mp4", "/dl", time.time(), 1),
        )
        conn.execute(
            "INSERT INTO downloads (url, out_dir, created_at) VALUES (?,?,?)",
            ("https://example.com/b.mp4", "/dl", time.time()),
        )
    with db.connect(path) as conn:
        rows = conn.execute(
            "SELECT url, convert_mp3 FROM downloads ORDER BY id"
        ).fetchall()
    assert bool(rows[0]["convert_mp3"]) is True
    assert bool(rows[1]["convert_mp3"]) is False


def test_migration_caps_connections_for_stock_aria2(tmp_path):
    path = tmp_path / "cove.db"
    conn = sqlite3.connect(path)
    conn.executescript(db.SCHEMA)
    conn.execute("PRAGMA user_version = 3")
    conn.execute(
        "INSERT INTO downloads (url, out_dir, connections, created_at) VALUES (?,?,?,?)",
        ("https://example.com/large.bin", "/dl", 32, time.time()),
    )
    conn.commit()
    conn.close()

    db.init(path)

    with db.connect(path) as conn:
        row = conn.execute("SELECT connections FROM downloads").fetchone()
    assert row["connections"] == 16
