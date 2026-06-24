"""상태 점검 (PING/관리포트) 및 결과 반영.

FW_PING_MODE:
  mock(기본) — IP를 시드로 한 결정적 의사결과(폴링해도 안 흔들림, ~85% 정상)
  tcp        — 실제로 관리포트 TCP 연결 시도 (사내망에서 도달 가능한 경우)
"""
import os
import socket
import random
from datetime import datetime, date

PING_MODE = os.environ.get("FW_PING_MODE", "mock")
WARN_EXPIRE_DAYS = int(os.environ.get("FW_WARN_EXPIRE_DAYS", "7"))


def _expire_days(expire_at):
    if not expire_at:
        return None
    try:
        d = datetime.strptime(expire_at[:10], "%Y-%m-%d").date()
    except ValueError:
        return None
    return (d - date.today()).days


def _tcp_check(ip, port):
    t0 = datetime.now()
    try:
        with socket.create_connection((ip, int(port or 443)), timeout=1.5):
            pass
        return True, int((datetime.now() - t0).total_seconds() * 1000)
    except OSError:
        return False, None


def _mock_check(ip):
    rnd = random.Random(ip)          # IP 기준 결정적 → 폴링 간 안정
    val = rnd.random()
    return val > 0.15, int(2 + val * 40)


def check_health(fw):
    """fw: {ip, mgmt_port, expire_days} → 판정 dict."""
    if PING_MODE == "tcp":
        reachable, latency = _tcp_check(fw["ip"], fw.get("mgmt_port"))
    else:
        reachable, latency = _mock_check(fw["ip"])

    if not reachable:
        return {"reachable": 0, "api_auth_ok": 0, "status": "down", "latency_ms": latency}

    # 도달 가능 → 점검필요 판단 (API 키 만료 임박 등)
    exp = fw.get("expire_days")
    warn = exp is not None and exp <= WARN_EXPIRE_DAYS
    return {
        "reachable": 1,
        "api_auth_ok": 1,
        "status": "warn" if warn else "up",
        "latency_ms": latency,
    }


def update_health(conn, firewall_id):
    """장비 1대 점검 → firewall_health 이력 추가 + firewalls.status 갱신."""
    row = conn.execute(
        """SELECT f.id, f.ip, f.mgmt_port, s.api_key_expire_at
           FROM firewalls f LEFT JOIN firewall_secrets s ON s.firewall_id = f.id
           WHERE f.id = ?""",
        (firewall_id,),
    ).fetchone()
    if not row:
        return None

    h = check_health({
        "ip": row["ip"],
        "mgmt_port": row["mgmt_port"],
        "expire_days": _expire_days(row["api_key_expire_at"]),
    })
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    conn.execute(
        """INSERT INTO firewall_health(firewall_id, reachable, api_auth_ok, status, latency_ms)
           VALUES (?, ?, ?, ?, ?)""",
        (firewall_id, h["reachable"], h["api_auth_ok"], h["status"], h["latency_ms"]),
    )
    if h["status"] in ("up", "warn"):
        conn.execute(
            "UPDATE firewalls SET status = ?, last_seen_at = ?, updated_at = ? WHERE id = ?",
            (h["status"], now, now, firewall_id),
        )
    else:
        conn.execute(
            "UPDATE firewalls SET status = ?, updated_at = ? WHERE id = ?",
            (h["status"], now, firewall_id),
        )
    return h
