"""비밀번호·API 키 암호화 (Fernet/AES).

키 우선순위: 환경변수 FW_SECRET_KEY → 로컬 키파일(.secret_key, 자동 생성).
⚠️ 운영에서는 키를 DB·코드와 분리해 env/KMS로 주입하세요. 키파일 방식은 개발 편의용입니다.
"""
import os
from cryptography.fernet import Fernet

KEY_FILE = os.environ.get("FW_KEY_FILE", ".secret_key")


def _load_key() -> bytes:
    env = os.environ.get("FW_SECRET_KEY")
    if env:
        return env.encode()
    if os.path.exists(KEY_FILE):
        with open(KEY_FILE, "rb") as f:
            return f.read()
    key = Fernet.generate_key()
    with open(KEY_FILE, "wb") as f:
        f.write(key)
    return key


_f = Fernet(_load_key())


def enc(text):
    """str → 암호문 bytes (None/빈값도 안전)."""
    return _f.encrypt((text or "").encode())


def dec(blob):
    """암호문 bytes → str."""
    if not blob:
        return ""
    return _f.decrypt(blob).decode()
