import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.config import DEFAULT_FRONTEND_ORIGINS, get_settings
from app.db.session import get_db
from app.main import app


def test_health_reports_api_status(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "sabores-del-llano-api"}


def test_database_health_reports_missing_configuration(client, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)

    response = client.get("/health/db")

    assert response.status_code == 503
    assert response.json() == {"detail": "Database is not configured."}


def test_database_health_runs_simple_query(client, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "mysql+pymysql://not-used-in-test")
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    def override_get_db():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    try:
        response = client.get("/health/db")
    finally:
        app.dependency_overrides.pop(get_db, None)
        engine.dispose()

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "reachable"}


def test_cors_defaults_are_explicit_origins():
    assert DEFAULT_FRONTEND_ORIGINS == (
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    )
    assert "*" not in DEFAULT_FRONTEND_ORIGINS


def test_cors_rejects_wildcard_origins(monkeypatch):
    monkeypatch.setenv("FRONTEND_ORIGINS", "*")

    with pytest.raises(ValueError, match=r"explicit HTTP\(S\) origins"):
        get_settings()
