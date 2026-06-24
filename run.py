"""API 서버 실행 진입점 (PM2가 python으로 직접 실행하기 좋게)."""
import os
import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=os.environ.get("FW_HOST", "0.0.0.0"),
        port=int(os.environ.get("FW_PORT", "8414")),
    )
