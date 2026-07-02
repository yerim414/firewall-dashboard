"""방화벽 관리 대시보드 API (FastAPI)."""
from __future__ import annotations   # str | None 문법을 구버전 파이썬에서도 허용

import json
import os
import shutil
import sqlite3
import uuid
from datetime import datetime, date

from fastapi import FastAPI, HTTPException, Form, File, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

DOCS_DIR = os.environ.get("FW_DOCS_DIR", "docs")   # 업로드 PDF 저장 폴더

import db
import crypto
import health
import dbsync

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
    keys = row.keys()
    d = dict(row)
    d["api_key_expire_days"] = _expire_days(row["api_key_expire_at"]) if "api_key_expire_at" in keys else None
    d["auth_method"] = (row["auth_method"] if "auth_method" in keys and row["auth_method"] else "api_key")
    if with_secrets:
        d["password"] = crypto.dec(row["password_enc"]) if ("password_enc" in keys and row["password_enc"]) else ""
        if "auth_data_enc" in keys and row["auth_data_enc"]:
            try:
                d["auth"] = json.loads(crypto.dec(row["auth_data_enc"]))
            except Exception:  # noqa: BLE001
                d["auth"] = {}
        elif "api_key_enc" in keys and row["api_key_enc"]:   # legacy 단일 키
            d["auth"] = {"api_key": crypto.dec(row["api_key_enc"])}
        else:
            d["auth"] = {}
    for k in ("password_enc", "api_key_enc", "auth_data_enc", "api_key_expire_at"):
        d.pop(k, None)
    d["servers"] = _servers_for_ip(conn, row["ip"])
    return d


# ── 장비 ───────────────────────────────────────────────
@app.get("/api/firewalls")
def list_firewalls():
    with db.session() as conn:
        rows = conn.execute(
            """SELECT f.*, s.api_key_expire_at, s.auth_method
               FROM firewalls f LEFT JOIN firewall_secrets s ON s.firewall_id = f.id
               ORDER BY f.id"""
        ).fetchall()
        return [_firewall_dict(conn, r) for r in rows]


@app.get("/api/firewalls/{fid}")
def get_firewall(fid: int):
    with db.session() as conn:
        row = conn.execute(
            """SELECT f.*, s.password_enc, s.api_key_enc, s.api_key_expire_at, s.auth_method, s.auth_data_enc
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
    api_port: int | None = None
    gui_port: int | None = None
    ssh_port: int | None = 22
    version: str | None = None
    admin_id: str | None = None
    description: str | None = None         # 자유 메모
    password: str | None = None            # 콘솔/SSH 비밀번호
    auth_method: str | None = "api_key"    # API 인증 방식
    auth: dict | None = None               # {field: value}
    api_key_expire_at: str | None = None   # 'YYYY-MM-DD'


@app.post("/api/firewalls", status_code=201)
def create_firewall(body: NewFirewall):
    with db.session() as conn:
        try:
            cur = conn.execute(
                """INSERT INTO firewalls(vendor, alias, ip, mgmt_port, api_port, gui_port, ssh_port, version, admin_id, description, status)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'checking')""",
                (body.vendor, body.alias, body.ip, body.mgmt_port, body.api_port, body.gui_port, body.ssh_port,
                 body.version, body.admin_id, body.description),
            )
        except sqlite3.IntegrityError:
            raise HTTPException(409, "이미 등록된 IP입니다")
        fid = cur.lastrowid
        auth_json = json.dumps(body.auth or {}, ensure_ascii=False)
        conn.execute(
            """INSERT INTO firewall_secrets(firewall_id, password_enc, auth_method, auth_data_enc, api_key_expire_at)
               VALUES (?, ?, ?, ?, ?)""",
            (fid, crypto.enc(body.password), body.auth_method or "api_key", crypto.enc(auth_json), body.api_key_expire_at),
        )
        health.update_health(conn, fid)        # 추가 직후 PING 으로 상태 자동 확인
    return get_firewall(fid)


class EditFirewall(BaseModel):
    vendor: str | None = None
    alias: str | None = None
    ip: str | None = None
    mgmt_port: int | None = None
    api_port: int | None = None
    gui_port: int | None = None
    ssh_port: int | None = None
    version: str | None = None
    admin_id: str | None = None
    description: str | None = None
    password: str | None = None
    auth_method: str | None = None
    auth: dict | None = None
    api_key_expire_at: str | None = None


@app.patch("/api/firewalls/{fid}")
def update_firewall(fid: int, body: EditFirewall):
    data = body.model_dump(exclude_unset=True)
    with db.session() as conn:
        if not conn.execute("SELECT 1 FROM firewalls WHERE id = ?", (fid,)).fetchone():
            raise HTTPException(404, "장비를 찾을 수 없습니다")
        # firewalls 테이블 컬럼 갱신
        cols = {k: data[k] for k in ("vendor", "alias", "ip", "mgmt_port", "api_port", "gui_port", "ssh_port", "version", "admin_id", "description") if k in data}
        if cols:
            sets = ", ".join(f"{k} = ?" for k in cols)
            try:
                conn.execute(
                    f"UPDATE firewalls SET {sets}, updated_at = datetime('now') WHERE id = ?",
                    (*cols.values(), fid),
                )
            except sqlite3.IntegrityError:
                raise HTTPException(409, "이미 등록된 IP입니다")
        # 자격증명 갱신 (보낸 항목만)
        sec_sets, sec_vals = [], []
        if "password" in data:
            sec_sets.append("password_enc = ?"); sec_vals.append(crypto.enc(data["password"]))
        if "auth_method" in data:
            sec_sets.append("auth_method = ?"); sec_vals.append(data["auth_method"])
        if "auth" in data:
            sec_sets.append("auth_data_enc = ?"); sec_vals.append(crypto.enc(json.dumps(data["auth"] or {}, ensure_ascii=False)))
        if "api_key_expire_at" in data:
            sec_sets.append("api_key_expire_at = ?"); sec_vals.append(data["api_key_expire_at"])
        if sec_sets:
            sec_vals.append(fid)
            conn.execute(
                f"UPDATE firewall_secrets SET {', '.join(sec_sets)}, updated_at = datetime('now') WHERE firewall_id = ?",
                sec_vals,
            )
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


# ── 앱 설정 (공통 DB 계정) ──────────────────────────────
def _get_setting(conn, key):
    row = conn.execute("SELECT value FROM app_settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else None


def _set_setting(conn, key, value):
    conn.execute(
        "INSERT INTO app_settings(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )


class DbAccount(BaseModel):
    user: str | None = None
    password: str | None = None


@app.get("/api/settings")
def get_settings():
    with db.session() as conn:
        user = _get_setting(conn, "db_account_user")
        has_pass = _get_setting(conn, "db_account_pass") is not None
    if isinstance(user, (bytes, bytearray)):
        user = user.decode()
    return {"db_account_user": user, "has_db_account_pass": has_pass}


@app.put("/api/settings/db-account")
def set_db_account(body: DbAccount):
    with db.session() as conn:
        if body.user is not None:
            _set_setting(conn, "db_account_user", body.user)
        if body.password:                       # 비밀번호는 입력했을 때만 갱신
            _set_setting(conn, "db_account_pass", crypto.enc(body.password))
    return {"ok": True}


# ── 등록 서버 (서버 DB ↔ 인벤토리 IP 매칭) ──────────────
def _server_public(s):
    """서버 행 → 응답 dict (DB 비밀번호는 제외, 설정 여부만 플래그)."""
    d = dict(s)
    cols = s.keys()
    d.pop("db_pass_enc", None)
    d["has_db_pass"] = bool(s["db_pass_enc"]) if "db_pass_enc" in cols else False
    return d


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
            out.append({**_server_public(s), "registered_count": len(regs), "matched": matched, "orphan": orphan})
        return out


class NewServer(BaseModel):
    id: str
    short: str
    name: str
    host: str
    role: str | None = None
    db_type: str | None = None
    db_host: str | None = None
    db_port: int | None = None
    db_name: str | None = None
    db_user: str | None = None
    db_pass: str | None = None
    db_query: str | None = None


@app.post("/api/servers", status_code=201)
def create_server(body: NewServer):
    with db.session() as conn:
        try:
            conn.execute(
                """INSERT INTO servers(id, short, name, host, role, db_type, db_host, db_port, db_name, db_user, db_pass_enc, db_query)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (body.id, body.short, body.name, body.host, body.role,
                 body.db_type or None, body.db_host, body.db_port, body.db_name, body.db_user,
                 (crypto.enc(body.db_pass) if body.db_pass else None), body.db_query),
            )
        except sqlite3.IntegrityError:
            raise HTTPException(409, "이미 존재하는 서버 ID입니다")
    return {"ok": True}


class EditServer(BaseModel):
    short: str | None = None
    name: str | None = None
    host: str | None = None
    role: str | None = None
    db_type: str | None = None
    db_host: str | None = None
    db_port: int | None = None
    db_name: str | None = None
    db_user: str | None = None
    db_pass: str | None = None
    db_query: str | None = None


@app.patch("/api/servers/{sid}")
def update_server(sid: str, body: EditServer):
    data = body.model_dump(exclude_unset=True)
    cols = {}
    for k in ("short", "name", "host", "role"):
        if k in data:
            cols[k] = data[k]
    for k in ("db_type", "db_host", "db_port", "db_name", "db_user", "db_query"):
        if k in data:
            cols[k] = data[k] if data[k] not in ("",) else None
    if data.get("db_pass"):                       # 비밀번호는 입력했을 때만 갱신
        cols["db_pass_enc"] = crypto.enc(data["db_pass"])
    with db.session() as conn:
        if not conn.execute("SELECT 1 FROM servers WHERE id = ?", (sid,)).fetchone():
            raise HTTPException(404, "서버를 찾을 수 없습니다")
        if cols:
            sets = ", ".join(f"{k} = ?" for k in cols)
            conn.execute(f"UPDATE servers SET {sets} WHERE id = ?", (*cols.values(), sid))
    return {"ok": True}


@app.post("/api/servers/{sid}/sync")
def sync_server(sid: str):
    """서버 DB에 접속해 등록 방화벽 IP를 읽어와 등록현황을 교체."""
    with db.session() as conn:
        s = conn.execute("SELECT * FROM servers WHERE id = ?", (sid,)).fetchone()
        if not s:
            raise HTTPException(404, "서버를 찾을 수 없습니다")
        if not s["db_type"]:
            raise HTTPException(400, "DB 연동 설정이 없습니다")
        # 계정 우선순위: 서버별 계정(user+pass 둘 다) → 없으면 공통 DB 계정
        if s["db_user"] and s["db_pass_enc"]:
            user, password = s["db_user"], crypto.dec(s["db_pass_enc"])
        else:
            g_user = _get_setting(conn, "db_account_user")
            g_pass = _get_setting(conn, "db_account_pass")
            if not g_user:
                raise HTTPException(400, "DB 계정이 없습니다 (공통 DB 계정을 설정하거나 서버별 계정을 입력하세요)")
            user = g_user.decode() if isinstance(g_user, (bytes, bytearray)) else g_user
            password = crypto.dec(g_pass) if g_pass else ""
        try:
            ips = dbsync.fetch_ips(
                s["db_type"], s["db_host"], s["db_port"], s["db_name"], user, password, s["db_query"]
            )
        except Exception as e:  # noqa: BLE001
            raise HTTPException(502, f"동기화 실패: {e}")
        conn.execute("DELETE FROM server_registrations WHERE server_id = ?", (sid,))
        for ip in ips:
            conn.execute("INSERT OR IGNORE INTO server_registrations(server_id, ip) VALUES (?, ?)", (sid, ip))
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn.execute("UPDATE servers SET last_synced_at = ? WHERE id = ?", (now, sid))
    return {"synced": len(ips), "at": now}


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


# ── 벤더별 API 문서 (수동 관리) ─────────────────────────
@app.get("/api/vendor-docs")
def list_vendor_docs():
    with db.session() as conn:
        rows = conn.execute(
            "SELECT id, vendor, kind, title, url, file_name, file_orig, guide, memo FROM vendor_docs ORDER BY vendor, sort, id"
        ).fetchall()
        return [dict(r) for r in rows]


@app.post("/api/vendor-docs", status_code=201)
async def create_vendor_doc(
    vendor: str = Form(...),
    kind: str = Form(...),
    title: str = Form(...),
    url: str | None = Form(None),
    guide: str | None = Form(None),
    memo: str | None = Form(None),
    file: UploadFile | None = File(None),
):
    if kind not in ("web", "pdf", "gui", "related"):
        raise HTTPException(400, "잘못된 문서 종류")
    file_name = file_orig = None
    if kind == "pdf":
        if not file:
            raise HTTPException(400, "PDF 파일이 필요합니다")
        ext = os.path.splitext(file.filename or "")[1] or ".pdf"
        file_name = uuid.uuid4().hex + ext
        file_orig = file.filename
        os.makedirs(DOCS_DIR, exist_ok=True)
        with open(os.path.join(DOCS_DIR, file_name), "wb") as f:
            shutil.copyfileobj(file.file, f)
    with db.session() as conn:
        conn.execute(
            "INSERT INTO vendor_docs(vendor, kind, title, url, file_name, file_orig, guide, memo) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (vendor, kind, title, url, file_name, file_orig, guide, memo),
        )
    return {"ok": True}


@app.patch("/api/vendor-docs/{doc_id}")
async def update_vendor_doc(
    doc_id: int,
    title: str | None = Form(None),
    url: str | None = Form(None),
    guide: str | None = Form(None),
    memo: str | None = Form(None),
    file: UploadFile | None = File(None),
):
    with db.session() as conn:
        row = conn.execute("SELECT file_name FROM vendor_docs WHERE id = ?", (doc_id,)).fetchone()
        if not row:
            raise HTTPException(404, "문서를 찾을 수 없습니다")
        sets, vals = [], []
        for col, val in (("title", title), ("url", url), ("guide", guide), ("memo", memo)):
            if val is not None:                     # 전송된 필드만 갱신 (빈 문자열도 반영)
                sets.append(f"{col} = ?"); vals.append(val)
        if file is not None:                        # 새 파일 업로드 시 교체
            ext = os.path.splitext(file.filename or "")[1] or ".pdf"
            new_name = uuid.uuid4().hex + ext
            os.makedirs(DOCS_DIR, exist_ok=True)
            with open(os.path.join(DOCS_DIR, new_name), "wb") as f:
                shutil.copyfileobj(file.file, f)
            sets += ["file_name = ?", "file_orig = ?"]
            vals += [new_name, file.filename]
        if sets:
            vals.append(doc_id)
            conn.execute(f"UPDATE vendor_docs SET {', '.join(sets)} WHERE id = ?", vals)
    if file is not None and row["file_name"]:       # 이전 파일 삭제
        try:
            os.remove(os.path.join(DOCS_DIR, row["file_name"]))
        except OSError:
            pass
    return {"ok": True}


class DocOrder(BaseModel):
    ids: list[int]      # 새 순서대로의 문서 id 목록


@app.patch("/api/vendor-docs/reorder")
def reorder_vendor_docs(body: DocOrder):
    with db.session() as conn:
        for i, doc_id in enumerate(body.ids):
            conn.execute("UPDATE vendor_docs SET sort = ? WHERE id = ?", (i, doc_id))
    return {"ok": True}


@app.delete("/api/vendor-docs/{doc_id}", status_code=204)
def delete_vendor_doc(doc_id: int):
    with db.session() as conn:
        row = conn.execute("SELECT file_name FROM vendor_docs WHERE id = ?", (doc_id,)).fetchone()
        conn.execute("DELETE FROM vendor_docs WHERE id = ?", (doc_id,))
    if row and row["file_name"]:
        try:
            os.remove(os.path.join(DOCS_DIR, row["file_name"]))
        except OSError:
            pass


@app.get("/api/docs/files/{name}")
def download_doc_file(name: str):
    safe = os.path.basename(name)                    # 경로 탈출 방지
    path = os.path.join(DOCS_DIR, safe)
    if not os.path.exists(path):
        raise HTTPException(404, "파일을 찾을 수 없습니다")
    with db.session() as conn:
        row = conn.execute("SELECT file_orig FROM vendor_docs WHERE file_name = ?", (safe,)).fetchone()
    return FileResponse(path, filename=(row["file_orig"] if row and row["file_orig"] else safe))


# ── 프론트엔드 ─────────────────────────────────────────
@app.get("/")
def index():
    return FileResponse("index.html")
