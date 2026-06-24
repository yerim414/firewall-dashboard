"""SQLite 연결 헬퍼."""
import os
import sqlite3
from contextlib import contextmanager

DB_PATH = os.environ.get("FW_DB", "firewall.db")
SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "schema.sql")


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def session():
    """with db.session() as conn: ... — 정상 종료 시 commit, 항상 close."""
    conn = get_conn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    """schema.sql 적용 (CREATE TABLE IF NOT EXISTS 라 반복 호출 안전)."""
    with open(SCHEMA_PATH, encoding="utf-8") as f:
        ddl = f.read()
    with session() as conn:
        conn.executescript(ddl)
