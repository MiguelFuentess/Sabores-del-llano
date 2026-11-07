from collections.abc import Generator
from functools import lru_cache
import os
from pathlib import Path
import ssl

import certifi
from fastapi import HTTPException, status
from sqlalchemy import Engine, create_engine
from sqlalchemy.engine import URL, make_url
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

LOCAL_DB_HOSTS = {"localhost", "127.0.0.1", "::1", "not-used-in-test"}
MYSQL_POOL_RECYCLE_SECONDS = 280
MYSQL_CONNECT_TIMEOUT_SECONDS = 15
MYSQL_READ_TIMEOUT_SECONDS = 15
MYSQL_WRITE_TIMEOUT_SECONDS = 15
MYSQL_SESSION_TIME_ZONE = "-05:00"
_SSL_QUERY_KEYS = (
    "ssl",
    "ssl_ca",
    "ssl_capath",
    "ssl_verify_cert",
    "ssl_verify_identity",
    "ssl_check_hostname",
    "ssl_disabled",
)


def _parse_optional_bool(raw_value: str) -> bool | None:
    normalized = raw_value.strip().lower()
    if not normalized:
        return None
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError("DB_SSL_REQUIRED must be a boolean value (true/false).")


def _should_enable_mysql_ssl(
    url: URL,
    db_ssl_required_raw: str,
    db_ssl_ca_raw: str,
) -> bool:
    explicit_flag = _parse_optional_bool(db_ssl_required_raw)
    if explicit_flag is not None:
        return explicit_flag

    if str(url.query.get("ssl_disabled", "")).strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }:
        return False

    if db_ssl_ca_raw.strip():
        return True

    if any(
        key in url.query
        for key in (
            "ssl",
            "ssl_ca",
            "ssl_capath",
            "ssl_cert",
            "ssl_verify_cert",
            "ssl_verify_identity",
        )
    ):
        if str(url.query.get("ssl", "")).strip().lower() in {"0", "false", "no", "off"}:
            return False
        return True

    host = (url.host or "").strip().lower()
    if not host or host in LOCAL_DB_HOSTS:
        return False
    return True


def _build_mysql_ssl_context(url: URL, db_ssl_ca_raw: str) -> ssl.SSLContext:
    env_ca = db_ssl_ca_raw.strip()
    url_ca = str(url.query.get("ssl_ca", "")).strip()
    if env_ca:
        if not Path(env_ca).is_file():
            raise ValueError(f"DB_SSL_CA file does not exist: {env_ca}")
        ca_file = env_ca
    elif url_ca and Path(url_ca).is_file():
        ca_file = url_ca
    else:
        ca_file = certifi.where()

    ctx = ssl.create_default_context(cafile=ca_file)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ctx.verify_mode = ssl.CERT_REQUIRED
    ctx.check_hostname = True
    return ctx


@lru_cache(maxsize=8)
def _engine_for(
    database_url: str,
    db_ssl_required: str = "",
    db_ssl_ca: str = "",
) -> Engine:
    if not database_url.startswith("mysql"):
        return create_engine(
            database_url,
            pool_pre_ping=True,
        )

    url = make_url(database_url)
    connect_args: dict[str, object] = {
        "connect_timeout": MYSQL_CONNECT_TIMEOUT_SECONDS,
        "read_timeout": MYSQL_READ_TIMEOUT_SECONDS,
        "write_timeout": MYSQL_WRITE_TIMEOUT_SECONDS,
        "init_command": f"SET time_zone = '{MYSQL_SESSION_TIME_ZONE}'",
    }
    if _should_enable_mysql_ssl(url, db_ssl_required, db_ssl_ca):
        connect_args["ssl"] = _build_mysql_ssl_context(url, db_ssl_ca)
        url = url.difference_update_query(_SSL_QUERY_KEYS)
    elif "ssl_disabled" in url.query:
        url = url.difference_update_query(["ssl_disabled"])

    return create_engine(
        url,
        pool_pre_ping=True,
        pool_recycle=MYSQL_POOL_RECYCLE_SECONDS,
        connect_args=connect_args,
    )


def get_engine() -> Engine:
    database_url = get_settings().database_url
    if not database_url:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database is not configured.",
        )
    db_ssl_required = os.getenv("DB_SSL_REQUIRED", "").strip()
    db_ssl_ca = os.getenv("DB_SSL_CA", "").strip()
    return _engine_for(database_url, db_ssl_required, db_ssl_ca)


def get_db() -> Generator[Session, None, None]:
    engine = get_engine()
    session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    session = session_factory()
    try:
        yield session
    finally:
        session.close()
