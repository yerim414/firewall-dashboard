# 방화벽 관리 대시보드

사내 테스트 방화벽 통합 현황 + 등록 서버(IP 매칭) 관리. FastAPI + SQLite.

## 구성

| 파일 | 역할 |
|---|---|
| `index.html` | 프론트엔드 (단일 파일, 현재는 목업 데이터 내장) |
| `schema.sql` | DB 스키마 (firewalls / firewall_secrets / servers / server_registrations / firewall_health) |
| `db.py` | SQLite 연결·세션·init |
| `crypto.py` | 비밀번호·API 키 암호화(Fernet) |
| `health.py` | PING/관리포트 점검 + 상태 반영 |
| `main.py` | FastAPI API |
| `run.py` | API 실행 진입점 (uvicorn) |
| `poller.py` | PING 주기 수집 워커 |
| `seed.py` | 목업 데이터 주입 |
| `ecosystem.config.js` | PM2 (api + poller) |

## 처음 실행

```bash
# 1) 가상환경 + 의존성
python -m venv .venv
.venv\Scripts\activate            # (Linux/Mac) source .venv/bin/activate
pip install -r requirements.txt

# 2) DB 생성 + 목업 데이터
python seed.py

# 3) API 실행
python run.py                     # http://localhost:8414  (문서: /docs)
```

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
| DELETE | `/api/firewalls/{id}` | 삭제 |
| GET | `/api/servers` | 서버별 등록 현황 (matched + 인벤토리 없는 orphan) |

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
- 비밀번호·API 키는 `firewall_secrets` 에 **암호화** 저장. 평문 금지.
- 운영에서는 `FW_SECRET_KEY` 를 env/KMS 로 주입하고 `.secret_key` 파일·`firewall.db` 는 git 에 올리지 마세요.

## 다음 단계 (아직 미연결)
- `index.html` 은 현재 **목업 데이터 내장**. `fetch('/api/...')` 로 백엔드와 연결하는 작업이 남아 있음.
- 서버 DB 실제 동기화 잡(`server_registrations` 채우기)은 현재 seed 로 흉내만 냄.
