"""방화벽 관리 대시보드 API (FastAPI)."""
from __future__ import annotations   # str | None 문법을 구버전 파이썬에서도 허용

import sqlite3
from datetime import datetime, date

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

import db
import crypto
import health

app = FastAPI(title="방화벽 관리 API")


@app.on_event("startup")
def _startup():
    db.init_db()


# ── 공통 헬퍼 ──────────────────────────────────────────
def _expire_days(expire_at):
    if not expire_at:
        return None
    try:
        d = datetime.strptime(expire_at[:10], "%Y-%m-%d").date()
    except ValueError:
        return None
    return (d - date.today()).days


def _servers_for_ip(conn, ip):
    """장비 IP를 서버 DB(server_registrations)와 매칭해 등록 서버 목록 반환."""
    rows = conn.execute(
        """SELECT s.id, s.short, s.name, s.host, s.role
           FROM server_registrations r JOIN servers s ON s.id = r.server_id
           WHERE r.ip = ? ORDER BY s.id""",
        (ip,),
    ).fetchall()
    return [dict(r) for r in rows]


def _firewall_dict(conn, row, with_secrets=False):
    d = dict(row)
    d["api_key_expire_days"] = _expire_days(row["api_key_expire_at"]) if "api_key_expire_at" in row.keys() else None
    if with_secrets:
        d["password"] = crypto.dec(row["password_enc"]) if row["password_enc"] else ""
        d["api_key"] = crypto.dec(row["api_key_enc"]) if row["api_key_enc"] else ""
    for k in ("password_enc", "api_key_enc", "api_key_expire_at"):
        d.pop(k, None)
    d["servers"] = _servers_for_ip(conn, row["ip"])
    return d


# ── 장비 ───────────────────────────────────────────────
@app.get("/api/firewalls")
def list_firewalls():
    with db.session() as conn:
        rows = conn.execute(
            """SELECT f.*, s.api_key_expire_at
               FROM firewalls f LEFT JOIN firewall_secrets s ON s.firewall_id = f.id
               ORDER BY f.id"""
        ).fetchall()
        return [_firewall_dict(conn, r) for r in rows]


@app.get("/api/firewalls/{fid}")
def get_firewall(fid: int):
    with db.session() as conn:
        row = conn.execute(
            """SELECT f.*, s.password_enc, s.api_key_enc, s.api_key_expire_at
               FROM firewalls f LEFT JOIN firewall_secrets s ON s.firewall_id = f.id
               WHERE f.id = ?""",
            (fid,),
        ).fetchone()
        if not row:
            raise HTTPException(404, "장비를 찾을 수 없습니다")
        return _firewall_dict(conn, row, with_secrets=True)


class NewFirewall(BaseModel):
    vendor: str
    alias: str
    ip: str
    mgmt_port: int = 443
    version: str | None = None
    admin_id: str | None = None
    password: str | None = None
    api_key: str | None = None
    api_key_expire_at: str | None = None   # 'YYYY-MM-DD'


@app.post("/api/firewalls", status_code=201)
def create_firewall(body: NewFirewall):
    with db.session() as conn:
        try:
            cur = conn.execute(
                """INSERT INTO firewalls(vendor, alias, ip, mgmt_port, version, admin_id, status)
                   VALUES (?, ?, ?, ?, ?, ?, 'checking')""",
                (body.vendor, body.alias, body.ip, body.mgmt_port, body.version, body.admin_id),
            )
        except sqlite3.IntegrityError:
            raise HTTPException(409, "이미 등록된 IP입니다")
        fid = cur.lastrowid
        conn.execute(
            """INSERT INTO firewall_secrets(firewall_id, password_enc, api_key_enc, api_key_expire_at)
               VALUES (?, ?, ?, ?)""",
            (fid, crypto.enc(body.password), crypto.enc(body.api_key), body.api_key_expire_at),
        )
        health.update_health(conn, fid)        # 추가 직후 PING 으로 상태 자동 확인
    return get_firewall(fid)


@app.post("/api/firewalls/{fid}/ping")
def ping_firewall(fid: int):
    with db.session() as conn:
        if not conn.execute("SELECT 1 FROM firewalls WHERE id = ?", (fid,)).fetchone():
            raise HTTPException(404, "장비를 찾을 수 없습니다")
        health.update_health(conn, fid)
    return get_firewall(fid)


@app.delete("/api/firewalls/{fid}", status_code=204)
def delete_firewall(fid: int):
    with db.session() as conn:
        conn.execute("DELETE FROM firewalls WHERE id = ?", (fid,))


# ── 등록 서버 (서버 DB ↔ 인벤토리 IP 매칭) ──────────────
@app.get("/api/servers")
def list_servers():
    with db.session() as conn:
        out = []
        for s in conn.execute("SELECT * FROM servers ORDER BY id").fetchall():
            regs = conn.execute(
                "SELECT ip, external_ref, registered_at FROM server_registrations WHERE server_id = ? ORDER BY ip",
                (s["id"],),
            ).fetchall()
            matched, orphan = [], []
            for r in regs:
                fw = conn.execute(
                    "SELECT id, vendor, alias, ip, status FROM firewalls WHERE ip = ?", (r["ip"],)
                ).fetchone()
                (matched.append(dict(fw)) if fw else orphan.append(r["ip"]))
            out.append({**dict(s), "registered_count": len(regs), "matched": matched, "orphan": orphan})
        return out


class NewServer(BaseModel):
    id: str
    short: str
    name: str
    host: str
    role: str | None = None


@app.post("/api/servers", status_code=201)
def create_server(body: NewServer):
    with db.session() as conn:
        try:
            conn.execute(
                "INSERT INTO servers(id, short, name, host, role) VALUES (?, ?, ?, ?, ?)",
                (body.id, body.short, body.name, body.host, body.role),
            )
        except sqlite3.IntegrityError:
            raise HTTPException(409, "이미 존재하는 서버 ID입니다")
    return {"ok": True}


@app.delete("/api/servers/{sid}", status_code=204)
def delete_server(sid: str):
    with db.session() as conn:
        conn.execute("DELETE FROM servers WHERE id = ?", (sid,))


class NewReg(BaseModel):
    ip: str


@app.post("/api/servers/{sid}/registrations", status_code=201)
def add_registration(sid: str, body: NewReg):
    with db.session() as conn:
        if not conn.execute("SELECT 1 FROM servers WHERE id = ?", (sid,)).fetchone():
            raise HTTPException(404, "서버를 찾을 수 없습니다")
        try:
            conn.execute(
                "INSERT INTO server_registrations(server_id, ip) VALUES (?, ?)", (sid, body.ip)
            )
        except sqlite3.IntegrityError:
            raise HTTPException(409, "이미 등록된 IP입니다")
    return {"ok": True}


@app.delete("/api/servers/{sid}/registrations/{ip}", status_code=204)
def delete_registration(sid: str, ip: str):
    with db.session() as conn:
        conn.execute(
            "DELETE FROM server_registrations WHERE server_id = ? AND ip = ?", (sid, ip)
        )


# ── 프론트엔드 ─────────────────────────────────────────
@app.get("/")
def index():
    return FileResponse("index.html")
