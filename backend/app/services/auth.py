from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import (
    InvalidTokenError,
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from app.models import Usuario
from app.schemas.auth import LoginRequest, TokenResponse, UsuarioPublicResponse

# Hash precalculado para comparación en tiempo constante cuando el usuario no existe
_DUMMY_PASSWORD_HASH = hash_password("sabores-del-llano-dummy-password-verification")


def _require_auth_secret() -> str:
    secret_key = get_settings().auth_secret_key
    if not secret_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication is not configured.",
        )
    return secret_key


def authenticate_user(session: Session, payload: LoginRequest) -> Usuario:
    """Valida las credenciales contra la tabla `usuarios` y actualiza `ultimo_acceso`."""
    usuario = session.scalar(
        select(Usuario).where(Usuario.nombre_usuario == payload.nombre_usuario)
    )
    if usuario is None:
        # Ejecuta verificación contra un hash ficticio para mitigar ataques de temporización
        verify_password(payload.password, _DUMMY_PASSWORD_HASH)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales de acceso inválidas.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not verify_password(payload.password, usuario.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales de acceso inválidas.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not usuario.activo:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="La cuenta de usuario se encuentra inactiva.",
        )

    usuario.ultimo_acceso = datetime.now(timezone.utc).replace(tzinfo=None)
    session.commit()
    session.refresh(usuario)
    return usuario


def login_for_access_token(
    session: Session, payload: LoginRequest
) -> TokenResponse:
    """Autentica al usuario y emite un token Bearer firmado."""
    secret_key = _require_auth_secret()
    settings = get_settings()
    usuario = authenticate_user(session, payload)

    token, expires_in = create_access_token(
        user_id=usuario.id,
        username=usuario.nombre_usuario,
        secret_key=secret_key,
        expires_delta=timedelta(minutes=settings.access_token_expire_minutes),
    )
    return TokenResponse(
        access_token=token,
        token_type="bearer",
        expires_in=expires_in,
        usuario=UsuarioPublicResponse.model_validate(usuario),
    )


def resolve_user_from_token(session: Session, token: str) -> Usuario:
    """Decodifica el token Bearer, consulta el usuario en BD y verifica que esté activo."""
    secret_key = _require_auth_secret()
    try:
        claims = decode_access_token(token, secret_key=secret_key)
    except InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from None

    usuario = session.get(Usuario, claims.user_id)
    if usuario is None or usuario.nombre_usuario != claims.username:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="El usuario asociado al token no existe.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not usuario.activo:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="La cuenta de usuario se encuentra inactiva.",
        )

    return usuario
