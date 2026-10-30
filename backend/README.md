# Backend de Sabores del Llano — Fase inicial

Base de API con FastAPI. En esta fase solo incluye configuración, conexión opcional a MySQL, sesión por solicitud, rutas de salud y pruebas. No contiene modelos de negocio ni crea o modifica tablas.

## Requisitos

- Python 3.11 o superior.
- MySQL 8 disponible para comprobar `/health/db` (opcional para iniciar la API y ejecutar las pruebas).

## Instalar y configurar (PowerShell)

Desde la carpeta `backend`:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Edita `.env` y sustituye los marcadores de `DATABASE_URL` por la conexión que te entregue el administrador de MySQL. No compartas ni subas ese archivo. La URL debe usar el driver `mysql+pymysql`; codifica caracteres especiales de la contraseña como URL encoding. Ajusta `FRONTEND_ORIGINS` con el origen real desde el que se servirá el frontend, separado por comas. No se permiten orígenes comodín.

La configuración faltante de base de datos no impide arrancar la API. `/health/db` informará que no está configurada sin exponer la URL ni las credenciales.

## Ejecutar

```powershell
uvicorn app.main:app --reload
```

La API queda en `http://127.0.0.1:8000`. La documentación automática está en `/docs` y `/redoc`.

## Comprobaciones

```powershell
pytest
```

- `GET /health` comprueba la API sin depender de MySQL.
- `GET /health/db` ejecuta `SELECT 1` y responde con un estado genérico. Devuelve HTTP 503 si falta configuración o no se puede acceder a MySQL.

Las pruebas de salud usan SQLite en memoria únicamente como sustituto de conexión para la prueba; no crean ni necesitan tablas del negocio y no validan el esquema MySQL.

## Esquema pendiente de verificación

No se encontró un volcado SQL ni otra definición del esquema en el repositorio. Antes de crear modelos, relaciones o migraciones, aporta un volcado de solo estructura (`mysqldump --no-data`) o las salidas de `SHOW CREATE TABLE` para las tablas del sistema. No se incorporó Alembic porque todavía no se ha determinado cómo gestionar el esquema existente.
