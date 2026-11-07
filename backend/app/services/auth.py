from __future__ import annotations

from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import sys

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

if str(Path(__file__).resolve().parents[2]) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.core.config import get_settings, is_placeholder_value
from app.core.security import (
    InvalidTokenError,
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from app.models import Usuario
from app.schemas.auth import (
    AdminInitResult,
    LoginRequest,
    TokenResponse,
    UsuarioPublicResponse,
)

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


def initialize_admin_from_env(
    session: Session,
    *,
    commit: bool = True,
) -> AdminInitResult:
    """Crea de forma idempotente el usuario administrador inicial leyendo credenciales
    exclusivamente desde variables de entorno (ADMIN_INITIAL_USERNAME, ADMIN_INITIAL_PASSWORD,
    ADMIN_INITIAL_FULL_NAME). No sobrescribe usuarios existentes ni expone contraseñas."""
    raw_username = (os.getenv("ADMIN_INITIAL_USERNAME") or "").strip()
    raw_password = os.getenv("ADMIN_INITIAL_PASSWORD") or ""
    raw_full_name = (
        os.getenv("ADMIN_INITIAL_FULL_NAME") or "Administración Sabores del Llano"
    ).strip()

    if not raw_username:
        raise ValueError(
            "La variable de entorno ADMIN_INITIAL_USERNAME es obligatoria y no está configurada."
        )
    if is_placeholder_value(raw_username):
        raise ValueError(
            "ADMIN_INITIAL_USERNAME no puede usar un valor de plantilla o marcador."
        )
    if len(raw_username) > 80:
        raise ValueError(
            "ADMIN_INITIAL_USERNAME no puede superar los 80 caracteres."
        )
    if not raw_password:
        raise ValueError(
            "La variable de entorno ADMIN_INITIAL_PASSWORD es obligatoria y no está configurada."
        )
    if is_placeholder_value(raw_password):
        raise ValueError(
            "ADMIN_INITIAL_PASSWORD no puede usar un valor de plantilla o marcador."
        )
    if len(raw_password) < 8:
        raise ValueError(
            "ADMIN_INITIAL_PASSWORD debe tener al menos 8 caracteres por seguridad."
        )
    if not raw_full_name or len(raw_full_name) > 120:
        raise ValueError(
            "ADMIN_INITIAL_FULL_NAME debe tener entre 1 y 120 caracteres."
        )

    existing = session.scalar(
        select(Usuario).where(Usuario.nombre_usuario == raw_username)
    )
    if existing is not None:
        return AdminInitResult(
            creado=False,
            usuario=UsuarioPublicResponse.model_validate(existing),
            mensaje=(
                f"El usuario '{raw_username}' ya existe (id={existing.id}). "
                "No se duplicó el registro ni se sobrescribió su contraseña."
            ),
        )

    nuevo_admin = Usuario(
        nombre_usuario=raw_username,
        nombre_completo=raw_full_name,
        password_hash=hash_password(raw_password),
        activo=True,
    )
    session.add(nuevo_admin)
    if commit:
        session.commit()
        session.refresh(nuevo_admin)
    else:
        session.flush()

    return AdminInitResult(
        creado=True,
        usuario=UsuarioPublicResponse.model_validate(nuevo_admin),
        mensaje=f"Usuario administrador '{raw_username}' inicializado correctamente.",
    )


def _cli() -> None:
    import argparse
    import json

    from app.db.session import get_engine

    parser = argparse.ArgumentParser(
        description="Utilidad de inicialización segura del usuario administrador inicial."
    )
    parser.add_argument(
        "--init-admin",
        action="store_true",
        required=True,
        help="Inicializa el primer usuario administrador usando variables de entorno.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simula la creación dentro de un SAVEPOINT y revierte los cambios al finalizar.",
    )
    args = parser.parse_args()

    engine = get_engine()
    with Session(bind=engine, autoflush=False, expire_on_commit=False) as session:
        savepoint = session.begin_nested() if args.dry_run else None
        try:
            result = initialize_admin_from_env(session, commit=not args.dry_run)
            if args.dry_run and savepoint is not None:
                savepoint.rollback()
            print(
                json.dumps(
                    result.model_dump(mode="json"),
                    indent=2,
                    ensure_ascii=False,
                )
            )
        except Exception:
            if savepoint is not None and savepoint.is_active:
                savepoint.rollback()
            else:
                session.rollback()
            raise


if __name__ == "__main__":
    _cli()
