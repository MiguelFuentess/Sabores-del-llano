from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import (
    create_access_token,
    hash_password,
    verify_password,
)
from app.db.session import get_db, get_engine
from app.main import app
from app.models import Usuario

TEST_SECRET_KEY = "test-only-secret-key-for-jwt-signing-at-least-32-chars"


@pytest.fixture
def auth_session(monkeypatch):
    monkeypatch.setenv("AUTH_SECRET_KEY", TEST_SECRET_KEY)
    monkeypatch.setenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60")
    engine = get_engine()
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(
        bind=connection,
        autoflush=False,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture
def auth_client(client, auth_session):
    def override_get_db():
        yield auth_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield client
    finally:
        app.dependency_overrides.pop(get_db, None)


def _create_test_user(
    session: Session,
    *,
    nombre_usuario: str = "martha.admin",
    nombre_completo: str = "Doña Martha",
    plain_password: str = "ClaveSegura#2026",
    activo: bool = True,
) -> Usuario:
    user = Usuario(
        nombre_usuario=nombre_usuario,
        nombre_completo=nombre_completo,
        password_hash=hash_password(plain_password),
        activo=activo,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def test_password_hash_and_verification():
    hashed = hash_password("MiContrasenaSecreta123!")
    assert hashed.startswith("pbkdf2_sha256$310000$")
    assert "MiContrasenaSecreta123!" not in hashed
    assert len(hashed) <= 255
    assert verify_password("MiContrasenaSecreta123!", hashed) is True
    assert verify_password("OtraContrasena", hashed) is False
    assert verify_password("MiContrasenaSecreta123!", "hash-invalido") is False


def test_login_successful_updates_ultimo_acceso_and_hides_password_hash(
    auth_client, auth_session
):
    user = _create_test_user(auth_session)
    assert user.ultimo_acceso is None

    response = auth_client.post(
        "/auth/login",
        json={"nombre_usuario": "martha.admin", "password": "ClaveSegura#2026"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["expires_in"] == 3600
    assert isinstance(body["access_token"], str) and body["access_token"].count(".") == 2

    usuario_data = body["usuario"]
    assert usuario_data["id"] == user.id
    assert usuario_data["nombre_usuario"] == "martha.admin"
    assert usuario_data["nombre_completo"] == "Doña Martha"
    assert usuario_data["activo"] is True
    assert usuario_data["ultimo_acceso"] is not None
    assert "password_hash" not in usuario_data
    assert "password" not in usuario_data


def test_login_rejects_wrong_password(auth_client, auth_session):
    _create_test_user(auth_session)

    response = auth_client.post(
        "/auth/login",
        json={"nombre_usuario": "martha.admin", "password": "PasswordIncorrecto"},
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "Credenciales de acceso inválidas."}
    assert response.headers.get("WWW-Authenticate") == "Bearer"


def test_login_rejects_nonexistent_user(auth_client):
    response = auth_client.post(
        "/auth/login",
        json={"nombre_usuario": "usuario.inexistente", "password": "CualquierPassword"},
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "Credenciales de acceso inválidas."}


def test_login_rejects_inactive_user(auth_client, auth_session):
    _create_test_user(
        auth_session,
        nombre_usuario="usuario.inactivo",
        plain_password="ClaveSegura#2026",
        activo=False,
    )

    response = auth_client.post(
        "/auth/login",
        json={"nombre_usuario": "usuario.inactivo", "password": "ClaveSegura#2026"},
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "La cuenta de usuario se encuentra inactiva."}


def test_protected_route_me_succeeds_with_valid_token(auth_client, auth_session):
    user = _create_test_user(auth_session)
    login_resp = auth_client.post(
        "/auth/login",
        json={"nombre_usuario": "martha.admin", "password": "ClaveSegura#2026"},
    )
    token = login_resp.json()["access_token"]

    me_resp = auth_client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert me_resp.status_code == 200
    me_data = me_resp.json()
    assert me_data["id"] == user.id
    assert me_data["nombre_usuario"] == "martha.admin"
    assert me_data["nombre_completo"] == "Doña Martha"
    assert "password_hash" not in me_data


def test_protected_route_me_rejects_missing_credentials(auth_client):
    response = auth_client.get("/auth/me")

    assert response.status_code == 401
    assert response.json() == {
        "detail": "No se proporcionaron credenciales de autenticación."
    }
    assert response.headers.get("WWW-Authenticate") == "Bearer"


def test_protected_route_me_rejects_tampered_or_malformed_token(
    auth_client, auth_session
):
    _create_test_user(auth_session)
    login_resp = auth_client.post(
        "/auth/login",
        json={"nombre_usuario": "martha.admin", "password": "ClaveSegura#2026"},
    )
    token = login_resp.json()["access_token"]
    tampered_token = token[:-4] + ("aaaa" if not token.endswith("aaaa") else "bbbb")

    resp_tampered = auth_client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {tampered_token}"},
    )
    assert resp_tampered.status_code == 401

    resp_malformed = auth_client.get(
        "/auth/me",
        headers={"Authorization": "Bearer token-sin-estructura"},
    )
    assert resp_malformed.status_code == 401


def test_protected_route_me_rejects_expired_token(auth_client, auth_session):
    user = _create_test_user(auth_session)
    past_time = datetime.now(timezone.utc) - timedelta(hours=2)
    expired_token, _ = create_access_token(
        user_id=user.id,
        username=user.nombre_usuario,
        secret_key=TEST_SECRET_KEY,
        expires_delta=timedelta(minutes=30),
        now=past_time,
    )

    response = auth_client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {expired_token}"},
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "El token de acceso ha expirado."}


def test_protected_route_me_rejects_user_deactivated_after_login(
    auth_client, auth_session
):
    user = _create_test_user(auth_session)
    login_resp = auth_client.post(
        "/auth/login",
        json={"nombre_usuario": "martha.admin", "password": "ClaveSegura#2026"},
    )
    token = login_resp.json()["access_token"]

    # Desactivar usuario después de haber emitido el token
    user.activo = False
    auth_session.commit()

    me_resp = auth_client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert me_resp.status_code == 403
    assert me_resp.json() == {"detail": "La cuenta de usuario se encuentra inactiva."}


def test_auth_config_validates_secret_length(monkeypatch):
    monkeypatch.setenv("AUTH_SECRET_KEY", "clave-demasiado-corta")
    with pytest.raises(ValueError, match="at least 32 characters"):
        get_settings()
