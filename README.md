# 방화벽 관리 대시보드

사내 방화벽 통합 관리 — 장비 인벤토리, 서버 DB 동기화(등록 현황 IP 매칭), 벤더별 API 문서까지 한 화면에서. **FastAPI + SQLite + 바닐라 JS**.

## 주요 기능

- **장비 목록** — 검색·상태 필터·벤더 트리·정렬·페이지네이션, 상태는 PING으로 자동 판정
- **장비 상세** — 콘솔 계정·비밀번호·API 인증정보(암호화 저장→복호화 표시), 설명 메모, 즉시 재점검
- **벤더별 인증 방식** — 장비 추가 시 벤더에 맞는 인증 필드 자동 표시 (REST API Key / Client ID+Secret / 공통 ID·PW+포트 / 없음)
- **등록 서버** — 각 서버 **DB에 접속해 등록 방화벽 IP를 동기화**(PostgreSQL/MySQL), 인벤토리와 IP 매칭 + 미관리 IP(드리프트) 표시. 서버들에 공통으로 쓰는 읽기전용 **공통 DB 계정** 지원
- **API 문서** — 벤더별 문서를 **수동 관리**. 웹 링크 / PDF 업로드 / GUI 확인 안내 / 관련 문서 + 메모, 드래그로 순서 정렬
- **통계** — 상태 도넛 · 벤더 분포 · 문서 종류별 현황
- **다크 모드 / 사이드바 접기**
- **관리자 모드** — 좌측 로고 5연타 + 패스코드로 진입. 장비·서버·문서의 추가/수정/삭제, DB 동기화 등 관리 기능

## 구성

| 파일 | 역할 |
|---|---|
| `index.html` | 프론트엔드 (단일 파일, `/api` 와 fetch 연동) |
| `schema.sql` | DB 스키마 (firewalls / firewall_secrets / servers / server_registrations / firewall_health / app_settings / vendor_docs) |
| `db.py` | SQLite 연결·세션·init + 컬럼 마이그레이션 |
| `crypto.py` | 비밀번호·API 키 암호화(Fernet) |
| `health.py` | PING/관리포트 점검 + 상태 반영 |
| `dbsync.py` | 외부 서버 DB(PostgreSQL/MySQL) 접속 → 등록 방화벽 IP 조회 |
| `main.py` | FastAPI API |
| `run.py` | API 실행 진입점 (uvicorn) |
| `poller.py` | PING 주기 수집 워커 |
| `seed.py` | 데모용 목업 데이터 주입 |
| `ecosystem.config.js` | PM2 (api + poller) |
| `docs/` | 업로드된 PDF 저장 폴더 (자동 생성, git 제외) |

## 처음 실행

```bash
# 1) 가상환경 + 의존성
python -m venv .venv
.venv\Scripts\activate            # (Linux/Mac) source .venv/bin/activate
pip install -r requirements.txt

# 2) (선택) DB 생성 + 데모 데이터 — 실배포 시엔 생략
python seed.py

# 3) API 실행
python run.py                     # http://localhost:8414  (API 문서: /docs)
```

> ⚠️ 화면은 반드시 **http://localhost:8414** 로 접속하세요. `index.html` 을 파일(`file://`)로 직접 열면 `fetch('/api/...')` 가 동작하지 않습니다.

## 리눅스 서버 배포

> Python **3.10+** 권장.

```bash
# 0) 사전 패키지  (Ubuntu/Debian: apt / RHEL·CentOS·Rocky: dnf)
sudo apt install -y python3 python3-venv python3-pip git      # 또는: sudo dnf install -y python3 git

# 1) clone + 가상환경 + 의존성
git clone https://github.com/yerim414/firewall-dashboard.git
cd firewall-dashboard
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt        # fastapi, pymysql/psycopg2(DB동기화), python-multipart(PDF업로드) 등

# 2) 암호화 키 고정 (운영 필수: 재시작해도 저장된 비밀 복호화 유지)
export FW_SECRET_KEY=$(python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
echo "FW_SECRET_KEY=$FW_SECRET_KEY"     # 이 값을 보관하고 항상 동일하게 주입

# 3) 실행 (테스트)
python run.py                           # 0.0.0.0:8414
```

접속: `http://<서버IP>:8414` (필요 시 포트 개방: `ufw allow 8414/tcp` 또는 firewalld)

### PM2 로 상시 구동 (권장)

```bash
sudo apt install -y nodejs npm && sudo npm install -g pm2   # (RHEL: dnf install -y nodejs)

# ⚠️ pm2 는 반드시 venv 파이썬으로 실행해야 함 (안 그러면 pymysql 등 못 찾음).
#    restart 로는 interpreter 가 안 바뀌므로 delete 후 start 로 등록:
pm2 start run.py    --name fw-api    --interpreter "$(pwd)/.venv/bin/python"
pm2 start poller.py --name fw-poller --interpreter "$(pwd)/.venv/bin/python"
pm2 save && pm2 startup     # 출력되는 명령 복붙 → 부팅 시 자동 시작
```
> `FW_SECRET_KEY` 를 export 한 셸에서 `pm2 start` 하면 그 값이 프로세스에 전달됩니다 (api·poller 동일 키 필요).

### 업데이트

```bash
git pull
source .venv/bin/activate && pip install -r requirements.txt   # 새 의존성 있을 때
pm2 restart fw-api fw-poller
```
> 스키마 변경분은 앱 시작 시 `db.init_db()` 가 **컬럼/테이블 자동 추가**(ALTER) 하며 **기존 데이터는 유지**됩니다.
> 실제 장비 상태를 ping 으로 확인하려면 `FW_PING_MODE=tcp` (기본은 데모용 `mock`).

## 배포 후 데이터 세팅 (관리자 모드)

DB 데이터(`firewall.db`)와 업로드 파일(`docs/`)은 git 으로 넘어가지 않으므로, 서버에서 한 번 채워야 합니다.

1. **공통 DB 계정** — 등록 서버 탭 → `🔑 공통 DB 계정` 에 읽기전용 계정 입력 (각 서버 DB에 동일 계정을 미리 생성해 둘 것, `GRANT SELECT`)
2. **서버 등록 + DB 연동** — `+ 서버 추가` → DB 종류·호스트·DB명·추출 쿼리 입력 → `↻ 동기화` 하면 방화벽 IP가 자동으로 채워짐
3. **API 문서** — 벤더 선택 → `+ 문서 추가` 로 링크·PDF·GUI 안내 등록

## 주요 API

| 메서드 | 경로 | 설명 |
|---|---|---|
| GET | `/api/firewalls` · `/api/firewalls/{id}` | 장비 목록 / 상세(비밀값 포함) |
| POST · PATCH · DELETE | `/api/firewalls` · `/{id}` | 장비 추가(직후 PING) / 수정 / 삭제 |
| POST | `/api/firewalls/{id}/ping` | 즉시 상태 재점검 |
| GET | `/api/servers` | 서버별 등록 현황 (matched + 드리프트 orphan) |
| POST · PATCH · DELETE | `/api/servers` · `/{id}` | 서버 추가 / 편집(DB연동 포함) / 삭제 |
| POST | `/api/servers/{id}/sync` | 서버 DB 접속 → 등록 IP 동기화 |
| POST · DELETE | `/api/servers/{id}/registrations[/{ip}]` | 수동 IP 등록 / 해제 |
| GET · PUT | `/api/settings` · `/api/settings/db-account` | 공통 DB 계정 조회 / 설정 |
| GET · POST · DELETE | `/api/vendor-docs` · `/{id}` | 문서 목록 / 추가(멀티파트) / 삭제 |
| PATCH | `/api/vendor-docs/reorder` | 문서 순서 저장 |
| GET | `/api/docs/files/{name}` | 업로드 PDF 다운로드 |

> ⚠️ 현재 모든 API는 **인증이 없습니다.** 관리자 모드는 화면(UI) 게이팅일 뿐이라, 실배포 전 인증/인가가 필요합니다.

## 환경변수

| 변수 | 기본 | 설명 |
|---|---|---|
| `FW_DB` | `firewall.db` | SQLite 파일 경로 |
| `FW_PORT` | `8414` | API 포트 |
| `FW_PING_MODE` | `mock` | `mock`=IP 시드 결정적 / `tcp`=실제 관리포트 연결 |
| `FW_POLL_INTERVAL` | `60` | 폴러 주기(초) |
| `FW_WARN_EXPIRE_DAYS` | `7` | API 키 만료 N일 이하 → 점검필요 |
| `FW_SECRET_KEY` | (자동) | 암호화 키. 미설정 시 `.secret_key` 자동 생성 |
| `FW_DOCS_DIR` | `docs` | 업로드 PDF 저장 폴더 |

## 보안 메모

- 비밀번호·API 키·DB 계정은 암호화(Fernet) 저장. 평문 금지.
- 운영에서는 `FW_SECRET_KEY` 를 env/KMS 로 주입. `.secret_key`·`firewall.db`·`docs/` 는 git 에 올리지 않음(`.gitignore`).
- 서버 DB 동기화용 계정은 **읽기전용(SELECT only)** 권장, 내부망으로 접근 제한.
- 모든 API에 인증이 없으므로 실배포 전 보호 필요.

## 남은 작업

- **API 인증/인가** — 관리자 엔드포인트를 실제 로그인/토큰 뒤로 보호 (현재 UI 게이팅뿐).
- **주기적 자동 동기화** — 현재 서버 DB 동기화는 수동(↻) 실행. 스케줄러로 자동화.
- `seed.py` 는 **데모 전용** — 실배포에선 실행하지 않음.
