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


# 기존 테이블에 나중에 추가된 컬럼 (없으면 ALTER 로 보강)
_SERVER_COLS = {
    "db_type": "TEXT", "db_host": "TEXT", "db_port": "INTEGER", "db_name": "TEXT",
    "db_user": "TEXT", "db_pass_enc": "BLOB", "db_query": "TEXT", "last_synced_at": "TEXT",
}
_SECRET_COLS = {
    "auth_method": "TEXT", "auth_data_enc": "BLOB",
}
_FIREWALL_COLS = {
    "description": "TEXT",
}
_VENDOR_DOCS_COLS = {
    "memo": "TEXT",
}


def _add_missing(conn, table, cols):
    existing = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
    for col, typ in cols.items():
        if col not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {typ}")


def init_db():
    """schema.sql 적용 (CREATE TABLE IF NOT EXISTS 라 반복 호출 안전) + 마이그레이션."""
    with open(SCHEMA_PATH, encoding="utf-8") as f:
        ddl = f.read()
    with session() as conn:
        conn.executescript(ddl)
        _add_missing(conn, "servers", _SERVER_COLS)
        _add_missing(conn, "firewall_secrets", _SECRET_COLS)
        _add_missing(conn, "firewalls", _FIREWALL_COLS)
        _add_missing(conn, "vendor_docs", _VENDOR_DOCS_COLS)
