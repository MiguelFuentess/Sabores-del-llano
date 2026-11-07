from dataclasses import dataclass
import os
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import load_dotenv


BACKEND_DIR = Path(__file__).resolve().parents[2]
load_dotenv(BACKEND_DIR / ".env")

DEFAULT_FRONTEND_ORIGINS = ("http://localhost:5173", "http://127.0.0.1:5173")
DEFAULT_ACCESS_TOKEN_EXPIRE_MINUTES = 480
_PLACEHOLDER_PREFIXES = (
    "REEMPLAZAR",
    "CHANGEME",
    "CHANGE_ME",
    "PLACEHOLDER",
    "YOUR_",
    "EXAMPLE_",
)
_PLACEHOLDER_EXACT = {
    "USUARIO",
    "CONTRASENA",
    "PASSWORD",
    "SECRET",
    "SECRET_KEY",
}


@dataclass(frozen=True)
class Settings:
    app_name: str
    environment: str
    database_url: str | None
    frontend_origins: tuple[str, ...]
    auth_secret_key: str | None = None
    access_token_expire_minutes: int = DEFAULT_ACCESS_TOKEN_EXPIRE_MINUTES


def is_placeholder_value(value: str) -> bool:
    normalized = value.strip().upper()
    if not normalized:
        return False
    return normalized in _PLACEHOLDER_EXACT or normalized.startswith(
        _PLACEHOLDER_PREFIXES
    )


def _has_placeholder_db_credentials(database_url: str) -> bool:
    parsed = urlsplit(database_url)
    for part in (parsed.username, parsed.password, parsed.hostname):
        if part and is_placeholder_value(part):
            return True
    return False


def get_settings() -> Settings:
    environment = (os.getenv("APP_ENV") or "development").strip().lower() or "development"
    is_production = environment == "production"

    configured_origins = os.getenv("FRONTEND_ORIGINS")
    if is_production and configured_origins is None:
        raise ValueError(
            "FRONTEND_ORIGINS must be explicitly configured when APP_ENV=production."
        )

    origins = (
        tuple(
            origin.strip().rstrip("/")
            for origin in configured_origins.split(",")
            if origin.strip()
        )
        if configured_origins is not None
        else DEFAULT_FRONTEND_ORIGINS
    )
    if is_production and not origins:
        raise ValueError(
            "FRONTEND_ORIGINS must contain at least one https:// origin when APP_ENV=production."
        )

    for origin in origins:
        parsed = urlsplit(origin)
        if (
            origin == "*"
            or is_placeholder_value(origin)
            or parsed.scheme not in {"http", "https"}
            or not parsed.netloc
            or parsed.path
            or parsed.query
            or parsed.fragment
            or parsed.username
            or parsed.password
        ):
            raise ValueError("FRONTEND_ORIGINS must contain explicit HTTP(S) origins only.")
        if is_production and (
            parsed.scheme != "https"
            or (parsed.hostname or "").lower() in {"localhost", "127.0.0.1", "::1"}
            or is_placeholder_value(parsed.hostname or "")
        ):
            raise ValueError(
                "FRONTEND_ORIGINS must use non-local https:// origins when APP_ENV=production."
            )

    raw_secret = (os.getenv("AUTH_SECRET_KEY") or "").strip()
    auth_secret_key = raw_secret or None
    if is_production and auth_secret_key is None:
        raise ValueError("AUTH_SECRET_KEY is required when APP_ENV=production.")
    if auth_secret_key is not None:
        if is_placeholder_value(auth_secret_key):
            raise ValueError(
                "AUTH_SECRET_KEY cannot use a placeholder or example value."
            )
        if len(auth_secret_key) < 32:
            raise ValueError("AUTH_SECRET_KEY must be at least 32 characters long.")

    raw_database_url = (os.getenv("DATABASE_URL") or "").strip()
    database_url = raw_database_url or None
    if is_production:
        if database_url is None:
            raise ValueError("DATABASE_URL is required when APP_ENV=production.")
        if is_placeholder_value(database_url) or _has_placeholder_db_credentials(
            database_url
        ):
            raise ValueError(
                "DATABASE_URL cannot use placeholder credentials when APP_ENV=production."
            )

    raw_expire = (os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES") or "").strip()
    if raw_expire:
        try:
            expire_minutes = int(raw_expire)
        except ValueError as exc:
            raise ValueError(
                "ACCESS_TOKEN_EXPIRE_MINUTES must be a positive integer."
            ) from exc
        if expire_minutes <= 0:
            raise ValueError("ACCESS_TOKEN_EXPIRE_MINUTES must be greater than zero.")
    else:
        expire_minutes = DEFAULT_ACCESS_TOKEN_EXPIRE_MINUTES

    return Settings(
        app_name="Sabores del Llano API",
        environment=environment,
        database_url=database_url,
        frontend_origins=origins,
        auth_secret_key=auth_secret_key,
        access_token_expire_minutes=expire_minutes,
    )
