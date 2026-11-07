from __future__ import annotations

import importlib.util
from pathlib import Path
import re
import ssl
import subprocess
from zoneinfo import ZoneInfo

import certifi
import pytest
from sqlalchemy import event, text

from app.core.config import BACKEND_DIR, get_settings
from app.db.base import TIDB_AUTO_ID_CACHE_DIRECTIVE
from app.db.init_schema import _cli as init_schema_cli
from app.db.init_schema import initialize_schema, render_mysql_schema_ddl
from app.db.session import (
    MYSQL_CONNECT_TIMEOUT_SECONDS,
    MYSQL_POOL_RECYCLE_SECONDS,
    MYSQL_SESSION_TIME_ZONE,
    _engine_for,
    get_engine,
)
from app.models import Base
from app.services.auth import initialize_admin_from_env

EXPECTED_TABLES_ORDERED = [
    "clientes",
    "usuarios",
    "productos",
    "presentaciones",
    "pedidos",
    "detalle_pedidos",
    "ventas",
    "detalle_ventas",
    "producciones",
    "movimientos_inventario",
    "cierres_diarios",
    "gastos",
]


def _capture_connect_kwargs(
    database_url: str,
    *,
    db_ssl_required: str = "",
    db_ssl_ca: str = "",
) -> tuple[object, dict[str, object]]:
    engine = _engine_for(database_url, db_ssl_required, db_ssl_ca)
    captured: dict[str, object] = {}

    @event.listens_for(engine, "do_connect")
    def _intercept_connect(dialect, conn_rec, cargs, cparams):
        captured.update(cparams)
        raise RuntimeError("intercepted-before-network")

    with pytest.raises(RuntimeError, match="intercepted-before-network"):
        engine.connect()

    return engine, captured


# ============================================================================
# CRIT-03: TLS / SSL, cryptography, certifi, pool_recycle y connect_timeout
# ============================================================================


def test_tls_runtime_dependencies_are_installed():
    assert importlib.util.find_spec("certifi") is not None
    assert importlib.util.find_spec("cryptography") is not None
    assert Path(certifi.where()).is_file()


def test_tidb_cloud_url_enables_verified_tls_and_strips_conflicting_query_params():
    tidb_url = (
        "mysql+pymysql://u123.root:SecretPass99"
        "@gateway01.us-east-1.prod.aws.tidbcloud.com:4000/sabores_del_llano"
        "?charset=utf8mb4&ssl_verify_cert=true&ssl_verify_identity=true"
    )
    engine, cparams = _capture_connect_kwargs(tidb_url)

    assert engine.pool._recycle == MYSQL_POOL_RECYCLE_SECONDS == 280
    assert cparams["connect_timeout"] == MYSQL_CONNECT_TIMEOUT_SECONDS == 15
    assert cparams["charset"] == "utf8mb4"
    # PyMySQL sobrescribiría el SSLContext si estos parámetros quedaran sueltos
    assert "ssl_verify_cert" not in cparams
    assert "ssl_verify_identity" not in cparams

    ssl_ctx = cparams.get("ssl")
    assert isinstance(ssl_ctx, ssl.SSLContext)
    assert ssl_ctx.minimum_version == ssl.TLSVersion.TLSv1_2
    assert ssl_ctx.verify_mode == ssl.CERT_REQUIRED
    assert ssl_ctx.check_hostname is True


def test_local_mysql_disables_tls_by_default_and_supports_explicit_override():
    local_url = "mysql+pymysql://sabores_app:SecretPass99@localhost:3306/sabores_del_llano"
    engine_plain, cparams_plain = _capture_connect_kwargs(local_url)
    assert engine_plain.pool._recycle == 280
    assert cparams_plain["connect_timeout"] == 15
    assert "ssl" not in cparams_plain

    _, cparams_forced = _capture_connect_kwargs(local_url, db_ssl_required="true")
    assert isinstance(cparams_forced.get("ssl"), ssl.SSLContext)

    with pytest.raises(ValueError, match="DB_SSL_REQUIRED"):
        _engine_for(local_url, "invalid-bool", "")

    with pytest.raises(ValueError, match="DB_SSL_CA"):
        _engine_for(local_url, "true", "/ruta/inexistente/ca-no-existe.pem")


# ============================================================================
# CRIT-04: Script SQL versionado y CLI idempotente de esquema
# ============================================================================


def test_sql_schema_file_defines_all_12_tables_in_valid_fk_order():
    sql_path = BACKEND_DIR / "sql" / "schema_tidb_mysql.sql"
    assert sql_path.is_file(), "Debe existir backend/sql/schema_tidb_mysql.sql"
    content = sql_path.read_text(encoding="utf-8")

    assert "SET time_zone = '-05:00';" in content
    table_blocks = re.findall(
        r"CREATE TABLE IF NOT EXISTS `(\w+)` \((.*?)\) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci /\*T!\[auto_id_cache\] AUTO_ID_CACHE=1 \*/;",
        content,
        flags=re.DOTALL,
    )
    created_in_order = [name for name, _ in table_blocks]
    assert created_in_order == EXPECTED_TABLES_ORDERED
    assert set(created_in_order) == set(Base.metadata.tables.keys())

    seen: set[str] = set()
    for table_name, body in table_blocks:
        referenced = re.findall(r"REFERENCES `(\w+)`", body)
        for parent_table in referenced:
            assert parent_table in seen, (
                f"La tabla `{table_name}` referencia `{parent_table}` antes de crearla"
            )
        seen.add(table_name)

    assert (
        "GENERATED ALWAYS AS ((`sobrante_real_base` - `existencia_calculada_base`)) STORED"
        in content
    )


def test_init_schema_cli_renders_ddl_and_verifies_live_schema(capsys):
    ddl = render_mysql_schema_ddl()
    for table_name in EXPECTED_TABLES_ORDERED:
        assert f"CREATE TABLE IF NOT EXISTS {table_name}" in ddl
    assert "ENGINE=InnoDB" in ddl
    assert "utf8mb4_0900_ai_ci" in ddl

    exit_code = init_schema_cli(["--print-sql"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "CREATE TABLE IF NOT EXISTS cierres_diarios" in captured.out

    settings = get_settings()
    if settings.database_url:
        engine = get_engine()
        check_summary = initialize_schema(engine, check_only=True)
        assert check_summary["esquema_completo"] is True
        assert check_summary["tablas_creadas"] == []
        assert check_summary["tablas_faltantes"] == []

        idempotent_summary = initialize_schema(engine, check_only=False)
        assert idempotent_summary["esquema_completo"] is True
        assert idempotent_summary["tablas_creadas"] == []


# ============================================================================
# CRIT-05: Validación estricta (fail-fast) en APP_ENV=production y plantillas
# ============================================================================


def test_auth_secret_rejects_long_placeholder_values_in_any_env(monkeypatch):
    monkeypatch.setenv(
        "AUTH_SECRET_KEY",
        "REEMPLAZAR_POR_CLAVE_SECRETA_ALEATORIA_DE_MINIMO_32_CARACTERES",
    )
    with pytest.raises(ValueError, match="placeholder"):
        get_settings()

    monkeypatch.setenv(
        "AUTH_SECRET_KEY",
        "CHANGEME_LONG_ENOUGH_TO_PASS_32_CHARS_CHECK_12345",
    )
    with pytest.raises(ValueError, match="placeholder"):
        get_settings()


def test_production_env_enforces_required_non_placeholder_variables_and_https(
    monkeypatch,
):
    valid_db = (
        "mysql+pymysql://prod_app:RealCryptographicPass2026"
        "@gateway01.us-east-1.prod.aws.tidbcloud.com:4000/sabores_del_llano"
    )
    valid_secret = "xK9vP2mQ8rL4nZ7wB3tF6yH1jD5sG0cA9eR2uY4iO8pW6qE3"
    valid_origin = "https://sabores-del-llano.onrender.com"

    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("DATABASE_URL", valid_db)
    monkeypatch.setenv("AUTH_SECRET_KEY", valid_secret)
    monkeypatch.setenv("FRONTEND_ORIGINS", valid_origin)

    ok_settings = get_settings()
    assert ok_settings.environment == "production"
    assert ok_settings.frontend_origins == (valid_origin,)

    # 1. Falta FRONTEND_ORIGINS
    monkeypatch.delenv("FRONTEND_ORIGINS")
    with pytest.raises(ValueError, match="FRONTEND_ORIGINS"):
        get_settings()

    # 2. FRONTEND_ORIGINS usa http:// o localhost en producción
    monkeypatch.setenv("FRONTEND_ORIGINS", "http://sabores-del-llano.onrender.com")
    with pytest.raises(ValueError, match="https://"):
        get_settings()

    monkeypatch.setenv("FRONTEND_ORIGINS", "https://localhost:5173")
    with pytest.raises(ValueError, match="https://"):
        get_settings()
    monkeypatch.setenv("FRONTEND_ORIGINS", valid_origin)

    # 3. Falta AUTH_SECRET_KEY en producción
    monkeypatch.delenv("AUTH_SECRET_KEY")
    with pytest.raises(ValueError, match="AUTH_SECRET_KEY is required"):
        get_settings()
    monkeypatch.setenv("AUTH_SECRET_KEY", valid_secret)

    # 4. Falta DATABASE_URL o usa credenciales de ejemplo en producción
    monkeypatch.delenv("DATABASE_URL")
    with pytest.raises(ValueError, match="DATABASE_URL is required"):
        get_settings()

    monkeypatch.setenv(
        "DATABASE_URL",
        "mysql+pymysql://USUARIO:CONTRASENA@gateway01.us-east-1.prod.aws.tidbcloud.com:4000/sabores_del_llano",
    )
    with pytest.raises(ValueError, match="placeholder credentials"):
        get_settings()


def test_initialize_admin_rejects_template_placeholders(monkeypatch):
    monkeypatch.setenv("ADMIN_INITIAL_USERNAME", "REEMPLAZAR_POR_USUARIO_ADMIN")
    monkeypatch.setenv("ADMIN_INITIAL_PASSWORD", "ClaveValidaReal#2026")
    with pytest.raises(ValueError, match="ADMIN_INITIAL_USERNAME"):
        initialize_admin_from_env(None, commit=False)  # type: ignore[arg-type]

    monkeypatch.setenv("ADMIN_INITIAL_USERNAME", "luz.admin")
    monkeypatch.setenv(
        "ADMIN_INITIAL_PASSWORD",
        "REEMPLAZAR_POR_CONTRASENA_SEGURA_DE_MINIMO_8_CARACTERES",
    )
    with pytest.raises(ValueError, match="ADMIN_INITIAL_PASSWORD"):
        initialize_admin_from_env(None, commit=False)  # type: ignore[arg-type]


# ============================================================================
# IMP-03, IMP-04 e IMP-05: .gitignore/dist, AUTO_ID_CACHE + UTC-5 y tzdata
# ============================================================================


def test_dist_directory_is_ignored_and_untracked_in_git():
    repo_root = BACKEND_DIR.parent
    gitignore_text = (repo_root / ".gitignore").read_text(encoding="utf-8")
    assert "dist/" in gitignore_text

    tracked_dist = subprocess.run(
        ["git", "ls-files", "dist"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=True,
    )
    assert tracked_dist.stdout.strip() == ""


def test_tidb_auto_id_cache_and_colombia_session_timezone():
    ddl = render_mysql_schema_ddl()
    assert "SET time_zone = '-05:00';" in ddl
    assert ddl.count(TIDB_AUTO_ID_CACHE_DIRECTIVE) == 12

    tidb_url = (
        "mysql+pymysql://u123.root:SecretPass99"
        "@gateway01.us-east-1.prod.aws.tidbcloud.com:4000/sabores_del_llano"
    )
    _, cparams = _capture_connect_kwargs(tidb_url)
    assert cparams["init_command"] == f"SET time_zone = '{MYSQL_SESSION_TIME_ZONE}'"

    settings = get_settings()
    if settings.database_url:
        with get_engine().connect() as conn:
            active_tz = conn.execute(text("SELECT @@session.time_zone")).scalar()
            assert active_tz == "-05:00"


def test_tzdata_package_declared_and_america_bogota_zoneinfo_resolves():
    requirements_text = (BACKEND_DIR / "requirements.txt").read_text(encoding="utf-8")
    assert "tzdata>=" in requirements_text
    assert importlib.util.find_spec("tzdata") is not None

    bogota_tz = ZoneInfo("America/Bogota")
    assert bogota_tz.key == "America/Bogota"
