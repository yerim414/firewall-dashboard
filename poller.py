"""PING 주기 수집 워커 (PM2 별도 프로세스로 실행).

전체 장비를 FW_POLL_INTERVAL 초마다 점검해 firewalls.status / firewall_health 갱신.
실행: python poller.py
"""
import os
import time

import db
import health

INTERVAL = int(os.environ.get("FW_POLL_INTERVAL", "60"))


def poll_all():
    with db.session() as conn:
        ids = [r["id"] for r in conn.execute("SELECT id FROM firewalls").fetchall()]
        for fid in ids:
            health.update_health(conn, fid)
    print(f"[poller] {len(ids)} devices checked (mode={health.PING_MODE})", flush=True)


if __name__ == "__main__":
    db.init_db()
    print(f"[poller] start · interval={INTERVAL}s", flush=True)
    while True:
        try:
            poll_all()
        except Exception as e:  # noqa: BLE001
            print(f"[poller] error: {e}", flush=True)
        time.sleep(INTERVAL)
