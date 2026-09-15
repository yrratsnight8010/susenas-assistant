"""
Autentikasi berbasis JWT.

Versi Streamlit menyimpan status login di `st.session_state.account`,
yang otomatis "nempel" karena Streamlit mengelola sesi server-side per
browser tab. FastAPI tidak seperti itu -- API-nya stateless, jadi
setiap request harus membawa buktinya sendiri.

Solusinya: setelah login sukses (POST /api/v1/auth/login), server
menerbitkan JWT (access token) berisi username & role. Frontend
menyimpan token ini (localStorage) dan mengirimkannya di header
`Authorization: Bearer <token>` pada setiap request selanjutnya.
`get_current_user` di bawah ini men-decode & memvalidasi token itu --
inilah pengganti langsung dari `st.session_state.account`.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import get_settings

bearer_scheme = HTTPBearer(auto_error=True)


def create_access_token(username: str, role: str) -> str:
    settings = get_settings()
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {"sub": username, "role": role, "exp": expire}
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict:
    settings = get_settings()
    try:
        return jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sesi sudah kedaluwarsa, silakan login ulang.",
        ) from exc
    except jwt.InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token tidak valid.",
        ) from exc


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> dict:
    payload = decode_access_token(credentials.credentials)
    username = payload.get("sub")
    role = payload.get("role")
    if not username or not role:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token tidak valid.")
    return {"username": username, "role": role}


def require_role(*allowed_roles: str):
    """Dependency factory -- setara pengecekan `role ==` yang di versi
    Streamlit dilakukan manual di app.py (`if role == "instruktur"`)."""

    async def _checker(user: dict = Depends(get_current_user)) -> dict:
        if user["role"] not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Anda tidak memiliki akses ke fitur ini.",
            )
        return user

    return _checker
