from dataclasses import dataclass
import os
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import load_dotenv


BACKEND_DIR = Path(__file__).resolve().parents[2]
load_dotenv(BACKEND_DIR / ".env")

DEFAULT_FRONTEND_ORIGINS = ("http://localhost:5173", "http://127.0.0.1:5173")


@dataclass(frozen=True)
class Settings:
    app_name: str
    environment: str
    database_url: str | None
    frontend_origins: tuple[str, ...]


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

    return Settings(
        app_name="Sabores del Llano API",
        environment=os.getenv("APP_ENV", "development"),
        database_url=os.getenv("DATABASE_URL") or None,
        frontend_origins=origins,
    )
