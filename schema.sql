-- 방화벽 관리 대시보드 스키마 (SQLite / PostgreSQL 호환 지향)
-- 벤더는 TEXT(방법 A), 한 방화벽 = IP 1개(UNIQUE)

-- 1. 장비 인벤토리 (= 장비 목록, 마스터)
CREATE TABLE IF NOT EXISTS firewalls (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  vendor       TEXT    NOT NULL,
  alias        TEXT    NOT NULL,
  ip           TEXT    NOT NULL UNIQUE,             -- 🔑 매칭 키
  mgmt_port    INTEGER NOT NULL DEFAULT 443,
  version      TEXT,
  admin_id     TEXT,
  description  TEXT,                                -- 자유 메모/설명
  status       TEXT    NOT NULL DEFAULT 'checking', -- up|warn|down|checking (최신 health 캐시)
  last_seen_at TEXT,                                -- 마지막 정상 수집 시각
  created_at   TEXT    NOT NULL DEFAULT (datetime('now')),
  updated_at   TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- 2. 자격증명 (분리 + 암호화 저장)
CREATE TABLE IF NOT EXISTS firewall_secrets (
  firewall_id       INTEGER PRIMARY KEY REFERENCES firewalls(id) ON DELETE CASCADE,
  password_enc      BLOB,        -- 콘솔/SSH 로그인 비밀번호 (Fernet 암호화)
  api_key_enc       BLOB,        -- (legacy) 단일 REST API Key
  api_key_expire_at TEXT,        -- 'YYYY-MM-DD'
  auth_method       TEXT,        -- API 인증 방식: api_key | client_secret | userpass | token ...
  auth_data_enc     BLOB,        -- 인증 필드 암호화 JSON {field: value}
  updated_at        TEXT NOT NULL DEFAULT (datetime('now'))
);

-- 3. 내부 서버 (= 등록 서버)
--    db_* 가 설정되면 그 DB에 접속해 등록 방화벽 IP를 자동 동기화 (없으면 수동 등록)
CREATE TABLE IF NOT EXISTS servers (
  id             TEXT PRIMARY KEY,   -- 자유 식별자 (예: 'withflow')
  short          TEXT NOT NULL,
  name           TEXT NOT NULL,
  host           TEXT NOT NULL,
  role           TEXT,
  db_type        TEXT,               -- postgresql | mysql (없으면 수동 등록 전용)
  db_host        TEXT,
  db_port        INTEGER,
  db_name        TEXT,
  db_user        TEXT,
  db_pass_enc    BLOB,               -- 암호화 저장
  db_query       TEXT,               -- IP 추출 SELECT (첫 컬럼을 IP로 사용)
  last_synced_at TEXT
);

-- 4. 서버 DB에서 동기화한 등록 현황 (캐시/스냅샷). 매칭은 ip 기준
CREATE TABLE IF NOT EXISTS server_registrations (
  server_id     TEXT NOT NULL REFERENCES servers(id) ON DELETE CASCADE,
  ip            TEXT NOT NULL,   -- 🔑 서버 DB에 등록된 방화벽 IP
  external_ref  TEXT,            -- 서버 쪽 레코드 식별자
  registered_at TEXT,            -- 서버에 등록된 시점(서버 DB 값)
  synced_at     TEXT NOT NULL DEFAULT (datetime('now')),
  PRIMARY KEY (server_id, ip)
);
CREATE INDEX IF NOT EXISTS idx_reg_ip ON server_registrations(ip);

-- 5. 상태 점검 이력 (PING 결과)
CREATE TABLE IF NOT EXISTS firewall_health (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  firewall_id INTEGER NOT NULL REFERENCES firewalls(id) ON DELETE CASCADE,
  checked_at  TEXT NOT NULL DEFAULT (datetime('now')),
  reachable   INTEGER NOT NULL,  -- 0/1  ping·관리포트
  api_auth_ok INTEGER,           -- 0/1
  status      TEXT NOT NULL,     -- up|warn|down
  latency_ms  INTEGER
);
CREATE INDEX IF NOT EXISTS idx_health_fw ON firewall_health(firewall_id, checked_at);

-- 6. 앱 설정 (key-value) — 공통 DB 계정 등
CREATE TABLE IF NOT EXISTS app_settings (
  key   TEXT PRIMARY KEY,
  value BLOB
);
