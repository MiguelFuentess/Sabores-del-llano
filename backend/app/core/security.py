from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import secrets

PBKDF2_ALGORITHM = "pbkdf2_sha256"
PBKDF2_ITERATIONS = 310_000
PBKDF2_SALT_BYTES = 16


class InvalidTokenError(Exception):
    """Se lanza cuando un token es inválido, fue alterado o ha expirado."""


@dataclass(frozen=True)
class AccessTokenClaims:
    user_id: int
    username: str
    issued_at: datetime
    expires_at: datetime


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    try:
        return base64.urlsafe_b64decode((data + padding).encode("ascii"))
    except Exception as exc:
        raise InvalidTokenError("El formato del token no es válido.") from exc


def hash_password(
    plain_password: str, *, iterations: int = PBKDF2_ITERATIONS
) -> str:
    """Genera un hash seguro PBKDF2-HMAC-SHA256 con sal aleatoria criptográfica."""
    if not plain_password:
        raise ValueError("La contraseña no puede estar vacía.")
    if iterations < 100_000:
        raise ValueError("El número de iteraciones PBKDF2 debe ser al menos 100.000.")

    salt = secrets.token_bytes(PBKDF2_SALT_BYTES)
    derived = hashlib.pbkdf2_hmac(
        "sha256", plain_password.encode("utf-8"), salt, iterations
    )
    return (
        f"{PBKDF2_ALGORITHM}${iterations}$"
        f"{_b64url_encode(salt)}${_b64url_encode(derived)}"
    )


def verify_password(plain_password: str, stored_hash: str) -> bool:
    """Verifica en tiempo constante una contraseña contra su hash almacenado."""
    if not plain_password or not stored_hash:
        return False
    parts = stored_hash.split("$")
    if len(parts) != 4:
        return False
    algorithm, raw_iterations, salt_b64, hash_b64 = parts
    if algorithm != PBKDF2_ALGORITHM:
        return False
    try:
        iterations = int(raw_iterations)
        if iterations <= 0:
            return False
        salt = _b64url_decode(salt_b64)
        expected_hash = _b64url_decode(hash_b64)
    except Exception:
        return False

    candidate_hash = hashlib.pbkdf2_hmac(
        "sha256", plain_password.encode("utf-8"), salt, iterations
    )
    return hmac.compare_digest(candidate_hash, expected_hash)


def create_access_token(
    *,
    user_id: int,
    username: str,
    secret_key: str,
    expires_delta: timedelta,
    now: datetime | None = None,
) -> tuple[str, int]:
    """Crea un JWT firmado con HMAC-SHA256 (HS256) y retorna (token, expires_in_seconds)."""
    if not secret_key or len(secret_key) < 32:
        raise ValueError("Se requiere una clave secreta de al menos 32 caracteres.")

    issued_at = now or datetime.now(timezone.utc)
    if issued_at.tzinfo is None:
        issued_at = issued_at.replace(tzinfo=timezone.utc)
    expires_at = issued_at + expires_delta
    expires_in = max(1, int(expires_delta.total_seconds()))

    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "sub": str(user_id),
        "username": username,
        "iat": int(issued_at.timestamp()),
        "exp": int(expires_at.timestamp()),
    }

    header_segment = _b64url_encode(
        json.dumps(header, separators=(",", ":"), sort_keys=True).encode("utf-8")
    )
    payload_segment = _b64url_encode(
        json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    )
    signing_input = f"{header_segment}.{payload_segment}".encode("ascii")
    signature = hmac.new(
        secret_key.encode("utf-8"), signing_input, hashlib.sha256
    ).digest()
    token = f"{header_segment}.{payload_segment}.{_b64url_encode(signature)}"
    return token, expires_in


def decode_access_token(
    token: str,
    *,
    secret_key: str,
    now: datetime | None = None,
) -> AccessTokenClaims:
    """Valida firma y expiración de un token JWT HS256 y devuelve sus claims."""
    if not secret_key or len(secret_key) < 32:
        raise ValueError("Se requiere una clave secreta de al menos 32 caracteres.")
    if not token or token.count(".") != 2:
        raise InvalidTokenError("El formato del token no es válido.")

    header_segment, payload_segment, signature_segment = token.split(".")
    signing_input = f"{header_segment}.{payload_segment}".encode("ascii")
    expected_signature = hmac.new(
        secret_key.encode("utf-8"), signing_input, hashlib.sha256
    ).digest()
    provided_signature = _b64url_decode(signature_segment)

    if not hmac.compare_digest(provided_signature, expected_signature):
        raise InvalidTokenError("La firma del token no es válida.")

    try:
        header = json.loads(_b64url_decode(header_segment).decode("utf-8"))
        payload = json.loads(_b64url_decode(payload_segment).decode("utf-8"))
    except Exception as exc:
        raise InvalidTokenError("El contenido del token no es válido.") from exc

    if not isinstance(header, dict) or header.get("alg") != "HS256":
        raise InvalidTokenError("El algoritmo del token no es compatible.")
    if not isinstance(payload, dict):
        raise InvalidTokenError("El cuerpo del token no es válido.")

    try:
        user_id = int(payload["sub"])
        username = str(payload["username"])
        iat_ts = int(payload["iat"])
        exp_ts = int(payload["exp"])
    except (KeyError, TypeError, ValueError) as exc:
        raise InvalidTokenError("El token no contiene los atributos requeridos.") from exc

    if user_id <= 0 or not username:
        raise InvalidTokenError("El identificador de usuario en el token no es válido.")

    current_time = now or datetime.now(timezone.utc)
    if current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=timezone.utc)
    if int(current_time.timestamp()) >= exp_ts:
        raise InvalidTokenError("El token de acceso ha expirado.")

    return AccessTokenClaims(
        user_id=user_id,
        username=username,
        issued_at=datetime.fromtimestamp(iat_ts, tz=timezone.utc),
        expires_at=datetime.fromtimestamp(exp_ts, tz=timezone.utc),
    )
