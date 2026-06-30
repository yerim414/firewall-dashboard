"""외부 서버 DB(PostgreSQL / MySQL)에 접속해 등록된 방화벽 IP를 읽어온다.

쿼리 결과의 **첫 번째 컬럼**을 IP로 사용한다.
드라이버는 해당 DB 종류를 쓸 때만 import (없으면 그때 명확한 에러).
"""


def fetch_ips(db_type, host, port, dbname, user, password, query):
    rows = _run(db_type, host, port, dbname, user, password, query)
    seen, out = set(), []
    for r in rows:
        if not r:
            continue
        val = r[0]
        if val is None:
            continue
        ip = str(val).strip()
        if ip and ip not in seen:
            seen.add(ip)
            out.append(ip)
    return out


def _run(db_type, host, port, dbname, user, password, query):
    t = (db_type or "").lower()
    if t in ("postgresql", "postgres", "pg"):
        return _run_pg(host, port or 5432, dbname, user, password, query)
    if t in ("mysql", "mariadb"):
        return _run_mysql(host, port or 3306, dbname, user, password, query)
    raise ValueError(f"지원하지 않는 DB 종류: {db_type}")


def _run_pg(host, port, dbname, user, password, query):
    try:
        import psycopg2
    except ImportError:
        raise RuntimeError("psycopg2 미설치 — pip install psycopg2-binary")
    conn = psycopg2.connect(
        host=host, port=int(port), dbname=dbname, user=user, password=password, connect_timeout=5
    )
    try:
        cur = conn.cursor()
        cur.execute(query)
        return cur.fetchall()
    finally:
        conn.close()


def _run_mysql(host, port, dbname, user, password, query):
    try:
        import pymysql
    except ImportError:
        raise RuntimeError("pymysql 미설치 — pip install pymysql")
    conn = pymysql.connect(
        host=host, port=int(port), database=dbname, user=user, password=password, connect_timeout=5
    )
    try:
        cur = conn.cursor()
        cur.execute(query)
        return cur.fetchall()
    finally:
        conn.close()
