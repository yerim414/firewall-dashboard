// PM2 설정 — API 서버 + PING 폴러 두 프로세스
// 실행:  pm2 start ecosystem.config.js
// 가상환경을 쓰면 interpreter 를 venv 의 python 경로로 바꾸세요.
//   (Windows) ".\\.venv\\Scripts\\python.exe"   (Linux/Mac) "./.venv/bin/python"
module.exports = {
  apps: [
    {
      name: "fw-api",
      script: "run.py",
      interpreter: "python",
      env: { FW_PORT: "8414", FW_PING_MODE: "mock" },
    },
    {
      name: "fw-poller",
      script: "poller.py",
      interpreter: "python",
      env: { FW_POLL_INTERVAL: "60", FW_PING_MODE: "mock" },
    },
  ],
};
