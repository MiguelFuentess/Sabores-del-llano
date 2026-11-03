from dataclasses import dataclass
import os
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import load_dotenv


BACKEND_DIR = Path(__file__).resolve().parents[2]
load_dotenv(BACKEND_DIR / ".env")

DEFAULT_FRONTEND_ORIGINS = ("http://localhost:5173", "http://127.0.0.1:5173")
DEFAULT_ACCESS_TOKEN_EXPIRE_MINUTES = 480


@dataclass(frozen=True)
class Settings:
    app_name: str
    environment: str
    database_url: str | None
    frontend_origins: tuple[str, ...]
    auth_secret_key: str | None = None
    access_token_expire_minutes: int = DEFAULT_ACCESS_TOKEN_EXPIRE_MINUTES


def get_settings() -> Settings:
    configured_origins = os.getenv("FRONTEND_ORIGINS")
    origins = tuple(
        origin.strip().rstrip("/")
        for origin in configured_origins.split(",")
        if origin.strip()
    ) if configured_origins is not None else DEFAULT_FRONTEND_ORIGINS
    for origin in origins:
        parsed = urlsplit(origin)
        if (
            origin == "*"
            or parsed.scheme not in {"http", "https"}
            or not parsed.netloc
            or parsed.path
            or parsed.query
            or parsed.fragment
            or parsed.username
            or parsed.password
        ):
            raise ValueError("FRONTEND_ORIGINS must contain explicit HTTP(S) origins only.")

    raw_secret = (os.getenv("AUTH_SECRET_KEY") or "").strip()
    auth_secret_key = raw_secret or None
    if auth_secret_key is not None and len(auth_secret_key) < 32:
        raise ValueError("AUTH_SECRET_KEY must be at least 32 characters long.")

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
        environment=os.getenv("APP_ENV", "development"),
        database_url=os.getenv("DATABASE_URL") or None,
        frontend_origins=origins,
        auth_secret_key=auth_secret_key,
        access_token_expire_minutes=expire_minutes,
    )
