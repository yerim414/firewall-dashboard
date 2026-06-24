# 방화벽 관리 대시보드

사내 테스트 방화벽 통합 현황 + 등록 서버(IP 매칭) 관리. **FastAPI + SQLite + 바닐라 JS**.

## 주요 기능

- **장비 목록** — 검색·상태 필터·벤더 트리·정렬·페이지네이션, 상태는 PING으로 자동 판정
- **등록 서버** — 각 서버 DB에서 읽어온 등록 방화벽을 **IP로 매칭**, 인벤토리에 없는 IP(드리프트)도 표시
- **장비 상세** — 비밀번호·API 키(암호화 저장→복호화 표시), 등록 서버, 즉시 재점검
- **API 문서** — 벤더·버전별 문서 모아보기 (공개/사내/미제공)
- **통계** — 상태 도넛 · 벤더 분포 · 문서 현황
- **다크 모드 / 사이드바 접기**
- **숨은 관리자 모드** — 좌측 로고를 1.5초 내 5연타로 토글. 서버 추가/삭제, 서버에 방화벽 등록/해제, 장비 삭제 가능

## 구성

| 파일 | 역할 |
|---|---|
| `index.html` | 프론트엔드 (단일 파일, `/api` 와 fetch 연동) |
| `schema.sql` | DB 스키마 (firewalls / firewall_secrets / servers / server_registrations / firewall_health) |
| `db.py` | SQLite 연결·세션·init |
| `crypto.py` | 비밀번호·API 키 암호화(Fernet) |
| `health.py` | PING/관리포트 점검 + 상태 반영 |
| `main.py` | FastAPI API |
| `run.py` | API 실행 진입점 (uvicorn) |
| `poller.py` | PING 주기 수집 워커 |
| `seed.py` | 데모용 목업 데이터 주입 |
| `ecosystem.config.js` | PM2 (api + poller) |

## 처음 실행

```bash
# 1) 가상환경 + 의존성
python -m venv .venv
.venv\Scripts\activate            # (Linux/Mac) source .venv/bin/activate
pip install -r requirements.txt

# 2) DB 생성 + 데모 데이터 (실배포 시엔 생략 가능)
python seed.py

# 3) API 실행
python run.py                     # http://localhost:8414  (API 문서: /docs)
```

> ⚠️ 화면은 반드시 **http://localhost:8414** 로 접속하세요. `index.html` 을 파일(`file://`)로 직접 열면 `fetch('/api/...')` 가 동작하지 않습니다.

## PM2

```bash
pm2 start ecosystem.config.js     # fw-api + fw-poller
pm2 logs
pm2 save && pm2 startup           # 부팅 시 자동 시작
```
> 가상환경을 쓰면 `ecosystem.config.js` 의 `interpreter` 를 venv python 경로로 바꾸세요.

## 주요 API

| 메서드 | 경로 | 설명 |
|---|---|---|
| GET | `/api/firewalls` | 장비 목록 (등록 서버 포함, 비밀값 제외) |
| GET | `/api/firewalls/{id}` | 장비 상세 (비밀번호·API 키 포함) |
| POST | `/api/firewalls` | 장비 추가 → 추가 직후 PING |
| POST | `/api/firewalls/{id}/ping` | 즉시 상태 재점검 |
| DELETE | `/api/firewalls/{id}` | 장비 삭제 |
| GET | `/api/servers` | 서버별 등록 현황 (matched + 인벤토리 없는 orphan) |
| POST | `/api/servers` | 서버 추가 |
| DELETE | `/api/servers/{id}` | 서버 삭제 |
| POST | `/api/servers/{id}/registrations` | 서버 DB에 방화벽 IP 등록 |
| DELETE | `/api/servers/{id}/registrations/{ip}` | 등록 해제 |

> ⚠️ 현재 모든 API는 **인증이 없습니다**. 관리자 모드는 화면(UI) 게이팅일 뿐이라, 실배포 전 인증/인가가 필요합니다.

## 환경변수

| 변수 | 기본 | 설명 |
|---|---|---|
| `FW_DB` | `firewall.db` | SQLite 파일 경로 |
| `FW_PORT` | `8414` | API 포트 |
| `FW_PING_MODE` | `mock` | `mock`=IP 시드 결정적 / `tcp`=실제 관리포트 연결 |
| `FW_POLL_INTERVAL` | `60` | 폴러 주기(초) |
| `FW_WARN_EXPIRE_DAYS` | `7` | API 키 만료 N일 이하 → 점검필요 |
| `FW_SECRET_KEY` | (자동) | 암호화 키. 미설정 시 `.secret_key` 자동 생성 |

## 보안 메모

- 비밀번호·API 키는 `firewall_secrets` 에 **암호화** 저장 (평문 금지).
- 운영에서는 `FW_SECRET_KEY` 를 env/KMS 로 주입하고, `.secret_key`·`firewall.db` 는 git 에 올리지 마세요. (`.gitignore` 처리됨)
- 모든 API에 인증이 없으므로 실배포 전 보호 필요.

## 실배포 전 남은 작업

- **서버 DB 동기화 잡** — `server_registrations` 를 각 서버 DB 조회로 실제 채우기 (현재는 seed 가 흉내).
- **API 인증/인가** — 관리자 엔드포인트 보호.
- `seed.py` 는 **데모 전용** — 실배포에선 실행하지 않음. (스키마는 앱 시작 시 `db.init_db()` 가 자동 생성)
