import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes.auth import router as auth_router
from app.api.routes.catalog import router as catalog_router
from app.api.routes.customers import router as customers_router
from app.api.routes.demand import router as demand_router
from app.api.routes.health import router as health_router
from app.api.routes.orders import router as orders_router
from app.api.routes.production import router as production_router
from app.api.routes.sales import router as sales_router
from app.core.config import get_settings


settings = get_settings()
logging.basicConfig(level=logging.INFO)

origins = list(
    dict.fromkeys(
        [
            "https://sabores-del-llano-1.onrender.com",
            "http://localhost:5173",
            "http://localhost:3000",
            *settings.frontend_origins,
        ]
    )
)

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="API inicial para Sabores del Llano.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_origin_regex=(
        r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$"
        if settings.environment == "development"
        else None
    ),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)
app.include_router(health_router)
app.include_router(auth_router)
app.include_router(catalog_router)
app.include_router(customers_router)
app.include_router(orders_router)
app.include_router(production_router)
app.include_router(sales_router)
app.include_router(demand_router)


@app.exception_handler(Exception)
async def unexpected_error_handler(request: Request, exc: Exception) -> JSONResponse:
    logging.getLogger(__name__).exception(
        "Unhandled API error for %s %s", request.method, request.url.path
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "An unexpected server error occurred."},
    )
