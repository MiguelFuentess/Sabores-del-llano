from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.schema import CreateTable

MYSQL_TABLE_ARGS: dict[str, str] = {
    "mysql_engine": "InnoDB",
    "mysql_charset": "utf8mb4",
    "mysql_collate": "utf8mb4_0900_ai_ci",
}
TIDB_AUTO_ID_CACHE_DIRECTIVE = "/*T![auto_id_cache] AUTO_ID_CACHE=1 */"


@compiles(CreateTable, "mysql")
def _compile_mysql_create_table_with_tidb_auto_id(
    element: CreateTable,
    compiler,
    **kw,
) -> str:
    sql = compiler.visit_create_table(element, **kw).rstrip()
    if TIDB_AUTO_ID_CACHE_DIRECTIVE not in sql:
        sql = f"{sql} {TIDB_AUTO_ID_CACHE_DIRECTIVE}"
    return sql


class Base(DeclarativeBase):
    """Clase base declarativa de SQLAlchemy 2.0 para el esquema sabores_del_llano."""

    __table_args__ = MYSQL_TABLE_ARGS
