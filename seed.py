"""목업 데이터 주입 (index.html 의 DATA / SERVERS 기반).

실행: python seed.py
"""
from datetime import datetime, timedelta

import db
import crypto

# id, vendor, alias, ip, version, status, mgmt_port, admin_id, api_key, expire_days
# ⚠️ IP는 전부 사설(RFC1918) 대역을 여러 서브넷에 분산 — 실제 존재하지 않는 IP만 사용
FIREWALLS = [
    (53,  "Fortinet",   "jylee",             "192.168.140.201", "7.4.8",         "up",   443, "admin",   "fk_9a3d2f7c8b1e4a05", 120),
    (54,  "Fortinet",   "forti-vdom",        "10.10.20.18",     "6.2.10",        "warn", 443, "admin",   "fk_1b7e0c44a9f2d6h3", 8),
    (59,  "Fortinet",   "f_test",            "10.20.30.2",      "7.2.11",        "up",   443, "admin",   "fk_55c1aa90b2e7f8k1", 95),
    (67,  "Paloalto",   "palo-vm",           "172.20.10.3",     "11.1.6-h4",     "up",   443, "admin",   "LUFRP2x3ZitTQ0E9bn",  200),
    (61,  "Ahnlab",     "TG50B",             "10.30.40.2",      "3.1.2.15",      "down", 443, "root",    "al_70f3c1d8e9a2b4m5", 0),
    (62,  "Ahnlab",     "TG40A",             "172.18.5.12",     "2.7.5.27",      "up",   443, "root",    "al_22b9d0f7c3e1a8n6", 60),
    (80,  "Axgate",     "AXGATE-80D",        "10.50.1.2",       "aos-2.1.1.3",   "up",   443, "admin",   "ax_4d8e2a90b6f1c7p2", 150),
    (87,  "Paloalto",   "pa-440",            "192.168.210.30",  "10.1.3",        "warn", 443, "admin",   "LUFRPWtkOEhzbS1wYT",  4),
    (104, "MF2",        "SECUI MF2 300",     "172.19.8.15",     "4.3.8",         "up",   443, "mfadmin", "mf_61a0e3c9d2f7b8q4", 88),
    (108, "CheckPoint", "R81",               "10.60.7.131",     "R81",           "down", 443, "admin",   "cp_33d7f1a8b0e9c2r5", 0),
    (109, "Fortinet",   "Withnetworks_Main", "10.0.90.62",      "7.2.11",        "up",   443, "admin",   "fk_88a2c0e7d3f9b1s6", 110),
    (110, "Fortinet",   "With_Lab",          "192.168.210.254", "6.2.9",         "up",   443, "admin",   "fk_19f4b2a8c0e7d3t7", 70),
    (115, "Fortinet",   "SVR_18F",           "172.16.250.251",  "6.2.7",         "warn", 443, "admin",   "fk_4c8d1e0a9b2f7u8",  5),
    (122, "Bluemax",    "NGF_bluemax_20",    "172.16.250.20",   "3.0.1",         "up",   443, "admin",   "bm_70e2c1a8d9f3b0v9", 130),
    (125, "Bluemax",    "NGF_bluemax_19",    "172.16.250.19",   "3.0.1",         "up",   443, "admin",   "bm_15a8c0e7d2f9b1w0", 130),
    (133, "Bluemax",    "NGF_bluemax_18",    "172.16.250.18",   "3.0.1",         "up",   443, "admin",   "bm_92d1f0a8c3e7b2x1", 130),
    (137, "NexG",       "NexG-VPN",          "10.70.5.5",       "4.6-130629",    "up",   443, "admin",   "ng_46b0c1e8a9f2d7y2", 45),
    (138, "WINS",       "Sniper",            "10.40.3.130",     "SNIPER OS V2.8","up",   443, "admin",   "wn_28c9a0e7b1f3d6z3", 77),
    (60,  "Fortinet",   "forti-legacy",      "10.80.8.4",       "v5.6.5",        "down", 443, "admin",   "fk_07a1c8e0d9f2b3a4", 0),
    (0,   "AWS",        "aws-sg",            "172.31.24.193",   "-",             "up",   443, "-",       "AKIA9X0EXAMPLE7Q2",   365),
]

SERVERS = {
    "mgmt-01":   ("NMS",    "통합관제 NMS",   "10.10.10.11", "상태·트래픽 모니터링"),
    "siem-01":   ("SIEM",   "SIEM 로그수집",  "10.10.10.21", "보안로그 연동"),
    "auto-01":   ("AUTO",   "방화벽 자동화",  "10.10.10.31", "정책 배포·오케스트레이션"),
    "backup-01": ("BACKUP", "설정 백업 서버", "10.10.10.41", "주기적 config 백업"),
}

# 각 서버 DB에 등록된 방화벽 IP (서버 DB 조회 결과를 흉내). 일부는 인벤토리에 없는 IP(드리프트)
REGISTRATIONS = {
    "mgmt-01": ["192.168.140.201", "10.10.20.18", "10.20.30.2", "172.20.10.3", "10.30.40.2",
                "172.18.5.12", "10.50.1.2", "192.168.210.30", "10.60.7.131", "10.0.90.62",
                "192.168.210.254", "172.16.250.251", "172.16.250.20", "172.16.250.19", "172.16.250.18", "10.70.5.5"],
    "siem-01": ["192.168.140.201", "172.20.10.3", "192.168.210.30", "172.19.8.15", "10.0.90.62", "10.40.3.130", "10.99.0.10"],
    "auto-01": ["10.20.30.2", "172.20.10.3", "10.0.90.62", "192.168.210.254", "172.31.24.193"],
    "backup-01": ["172.18.5.12", "172.19.8.15", "10.0.90.62", "172.16.250.20", "172.16.250.19", "172.16.250.18", "172.16.250.99"],
}


def run():
    db.init_db()
    today = datetime.now().date()
    with db.session() as conn:
        for (fid, vendor, alias, ip, version, status, port, admin, api_key, exp) in FIREWALLS:
            last_seen = datetime.now().strftime("%Y-%m-%d %H:%M:%S") if status in ("up", "warn") else None
            conn.execute(
                """INSERT OR IGNORE INTO firewalls(id, vendor, alias, ip, mgmt_port, version, admin_id, status, last_seen_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (fid, vendor, alias, ip, port, version, admin, status, last_seen),
            )
            expire_at = (today + timedelta(days=exp)).isoformat() if exp > 0 else None
            conn.execute(
                """INSERT OR IGNORE INTO firewall_secrets(firewall_id, password_enc, api_key_enc, api_key_expire_at)
                   VALUES (?, ?, ?, ?)""",
                (fid, crypto.enc("P@ssw0rd!" + str(fid)), crypto.enc(api_key), expire_at),
            )

        for sid, (short, name, host, role) in SERVERS.items():
            conn.execute(
                "INSERT OR IGNORE INTO servers(id, short, name, host, role) VALUES (?, ?, ?, ?, ?)",
                (sid, short, name, host, role),
            )
            for ip in REGISTRATIONS.get(sid, []):
                conn.execute(
                    "INSERT OR IGNORE INTO server_registrations(server_id, ip) VALUES (?, ?)",
                    (sid, ip),
                )

    print(f"seed 완료: 방화벽 {len(FIREWALLS)}대, 서버 {len(SERVERS)}개")


if __name__ == "__main__":
    run()
