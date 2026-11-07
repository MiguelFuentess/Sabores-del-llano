# Backend de Sabores del Llano (FastAPI + SQLAlchemy 2.0)

API RESTful de **Sabores del Llano** construida con FastAPI, SQLAlchemy 2.0 y PyMySQL, preparada tanto para desarrollo local con MySQL 8.0+ como para despliegue en producción sobre **Render** y **TiDB Cloud Serverless**.

## Requisitos

- Python 3.11 o superior.
- MySQL 8.0+ local o un clúster **TiDB Cloud Serverless** (compatible con protocolo MySQL y TLS 1.2+).

## Instalación y configuración local (PowerShell)

Desde la carpeta `backend`:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Edita `backend/.env` y sustituye todos los marcadores (`USUARIO`, `CONTRASENA`, `REEMPLAZAR_*`) por valores reales. Nunca compartas ni subas `backend/.env` al repositorio.

## Aprovisionamiento del esquema (MySQL 8 / TiDB Cloud)

El proyecto ofrece dos mecanismos equivalentes e idempotentes para crear las **12 tablas** del dominio (`InnoDB`, `utf8mb4_0900_ai_ci`, claves foráneas, restricciones `CHECK` y columna calculada `cierres_diarios.diferencia_base`):

### Opción A — Comando CLI en Python (`Base.metadata.create_all`)

Desde la carpeta `backend`:

```powershell
# Crear las 12 tablas de forma idempotente (no sobrescribe datos existentes)
python -m app.db.init_schema

# Crear tablas + sembrar catálogo base (Hayaca y Lechona) + crear admin inicial
python -m app.db.init_schema --seed-catalog --init-admin

# Solo verificar que las 12 tablas existan (sin modificar la BD)
python -m app.db.init_schema --check
```

### Opción B — Script DDL SQL versionado

Ejecuta directamente `backend/sql/schema_tidb_mysql.sql` en el **SQL Editor** de TiDB Cloud o mediante cliente MySQL tras seleccionar la base de datos destino (`USE sabores_del_llano;`).

Después de crear las tablas por SQL, puedes inicializar el usuario administrador inicial con:

```powershell
python -m app.services.auth --init-admin
```

## Conexión segura TLS con TiDB Cloud Serverless

`app/db/session.py` configura automáticamente:

- **TLS 1.2+ verificado (`ssl.CERT_REQUIRED` + `check_hostname=True`)** usando el paquete de certificados raíz `certifi` siempre que el host de `DATABASE_URL` sea remoto (por ejemplo `*.tidbcloud.com`) o cuando `DB_SSL_REQUIRED=true`.
- **`connect_timeout=15`** para tolerar el arranque en frío (*cold start*) de clústeres gratuitos de TiDB Serverless.
- **`pool_pre_ping=True` y `pool_recycle=280`** para reciclar conexiones antes del cierre por inactividad en la nube (~300 s).
- Si se requiere una autoridad certificadora personalizada, puede indicarse su ruta en `DB_SSL_CA`.

## Validación estricta en producción (`APP_ENV=production`)

Cuando `APP_ENV=production`, `app/core/config.py` valida de inmediato al iniciar (`fail-fast`):

1. `DATABASE_URL` debe estar definida y no contener credenciales de plantilla (`USUARIO`, `CONTRASENA`, `REEMPLAZAR_*`).
2. `AUTH_SECRET_KEY` debe estar definida, tener mínimo 32 caracteres y no usar valores de ejemplo (`REEMPLAZAR_*`, `CHANGEME`).
3. `FRONTEND_ORIGINS` debe declararse explícitamente y contener únicamente orígenes remotos con `https://` (sin comodines `*` ni `localhost`).

## Ejecución y pruebas

```powershell
# Iniciar servidor de desarrollo (desde backend/)
uvicorn app.main:app --reload

# Ejecutar suite completa de pruebas (desde la raíz del repositorio)
.\backend\.venv\Scripts\python.exe -m pytest backend/tests/ -v
```
