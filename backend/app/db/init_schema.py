from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from sqlalchemy import Engine, inspect
from sqlalchemy.dialects import mysql
from sqlalchemy.orm import Session
from sqlalchemy.schema import CreateIndex, CreateTable

if str(Path(__file__).resolve().parents[2]) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.db.session import get_engine  # noqa: E402
from app.models import Base  # noqa: E402


def render_mysql_schema_ddl() -> str:
    """Genera el DDL de creación de tablas e índices para MySQL 8.0 / TiDB Cloud."""
    dialect = mysql.dialect()
    statements: list[str] = [
        "SET NAMES utf8mb4;",
        "SET time_zone = '-05:00';",
    ]
    for table in Base.metadata.sorted_tables:
        create_table_sql = str(
            CreateTable(table, if_not_exists=True).compile(dialect=dialect)
        ).strip()
        statements.append(f"{create_table_sql};")
        for index in table.indexes:
            create_idx_sql = str(CreateIndex(index).compile(dialect=dialect)).strip()
            statements.append(f"{create_idx_sql};")
    return "\n\n".join(statements) + "\n"


def initialize_schema(
    engine: Engine | None = None,
    *,
    check_only: bool = False,
) -> dict[str, object]:
    """Crea de forma idempotente las 12 tablas registradas en `Base.metadata`."""
    target_engine = engine or get_engine()
    expected_tables = [table.name for table in Base.metadata.sorted_tables]
    expected_set = set(expected_tables)

    existing_before = set(inspect(target_engine).get_table_names()) & expected_set
    if not check_only:
        Base.metadata.create_all(bind=target_engine, checkfirst=True)

    existing_after = set(inspect(target_engine).get_table_names()) & expected_set
    created_tables = [
        name for name in expected_tables if name in (existing_after - existing_before)
    ]
    missing_tables = [name for name in expected_tables if name not in existing_after]

    return {
        "esquema_completo": len(missing_tables) == 0,
        "modo_verificacion": check_only,
        "tablas_esperadas": expected_tables,
        "tablas_existentes_previas": [
            name for name in expected_tables if name in existing_before
        ],
        "tablas_creadas": created_tables,
        "tablas_faltantes": missing_tables,
    }


def _cli(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Inicializa o verifica de forma idempotente el esquema relacional "
            "de Sabores del Llano (MySQL 8.0 / TiDB Cloud Serverless)."
        )
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Verifica si las 12 tablas existen sin crear ni modificar estructuras.",
    )
    parser.add_argument(
        "--print-sql",
        action="store_true",
        help="Imprime el DDL MySQL/TiDB compilado desde SQLAlchemy sin conectar a la BD.",
    )
    parser.add_argument(
        "--seed-catalog",
        action="store_true",
        help="Inicializa de forma idempotente el catálogo base (Hayaca y Lechona).",
    )
    parser.add_argument(
        "--init-admin",
        action="store_true",
        help="Inicializa de forma idempotente el usuario administrador desde variables de entorno.",
    )
    args = parser.parse_args(argv)

    if args.print_sql:
        print(render_mysql_schema_ddl(), end="")
        return 0

    engine = get_engine()
    summary = initialize_schema(engine, check_only=args.check)

    if not args.check and summary["esquema_completo"]:
        if args.seed_catalog:
            from app.services.catalog import seed_initial_catalog

            with Session(bind=engine, autoflush=False, expire_on_commit=False) as session:
                catalog_result = seed_initial_catalog(session)
                summary["catalogo_inicial"] = catalog_result.model_dump(mode="json")

        if args.init_admin:
            from app.services.auth import initialize_admin_from_env

            with Session(bind=engine, autoflush=False, expire_on_commit=False) as session:
                admin_result = initialize_admin_from_env(session, commit=True)
                summary["admin_inicial"] = admin_result.model_dump(mode="json")

    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0 if summary["esquema_completo"] else 1


if __name__ == "__main__":
    raise SystemExit(_cli())
