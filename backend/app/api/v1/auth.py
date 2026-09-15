from fastapi import APIRouter, Depends, HTTPException, status

from app.core.config import get_settings, load_accounts
from app.core.security import create_access_token, get_current_user
from app.schemas.auth import LoginRequest, TokenResponse, UserInfo
from app.services.rag_pipeline import authenticate

router = APIRouter()


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Login dan dapatkan access token",
    description=(
        "Pengganti langsung dari form login di app.py Streamlit "
        "(`login_view`). Bedanya, di sini server tidak menyimpan sesi -- "
        "server hanya menerbitkan JWT yang harus disertakan frontend "
        "pada setiap request berikutnya (header `Authorization: Bearer <token>`)."
    ),
)
def login(payload: LoginRequest) -> TokenResponse:
    settings = get_settings()
    try:
        accounts = load_accounts(settings.accounts_file)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc

    if not accounts:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Belum ada akun terdaftar di accounts.json.",
        )

    account = authenticate(accounts, payload.username, payload.password)
    if account is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Username atau password salah.")

    token = create_access_token(account["username"], account["role"])
    return TokenResponse(access_token=token, username=account["username"], role=account["role"])


@router.get(
    "/me",
    response_model=UserInfo,
    summary="Info akun yang sedang login",
    description="Dipakai frontend untuk cek token yang tersimpan masih valid & tahu role user tanpa login ulang.",
)
def me(current_user: dict = Depends(get_current_user)) -> UserInfo:
    return UserInfo(**current_user)
