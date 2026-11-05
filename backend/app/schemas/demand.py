from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.customers import normalize_optional_str

HorizonteEstimacionLiteral = Literal[
    "proxima_semana",
    "proximo_mes",
    "proximo_trimestre",
]

TipoDiaOperativoLiteral = Literal[
    "sabado",
    "domingo",
    "festivo",
]

NivelConfianzaLiteral = Literal[
    "alta",
    "media",
    "baja",
]

OrigenEvaluacionLiteral = Literal[
    "datos_reales_y_operativos",
    "datos_sinteticos_advertencia",
    "muestra_insuficiente",
]

_HORIZONTE_ALIASES: dict[str, HorizonteEstimacionLiteral] = {
    "proxima_semana": "proxima_semana",
    "próxima semana": "proxima_semana",
    "proxima semana": "proxima_semana",
    "semana": "proxima_semana",
    "7_dias": "proxima_semana",
    "proximo_mes": "proximo_mes",
    "próximo mes": "proximo_mes",
    "proximo mes": "proximo_mes",
    "mes": "proximo_mes",
    "30_dias": "proximo_mes",
    "proximo_trimestre": "proximo_trimestre",
    "próximo trimestre": "proximo_trimestre",
    "proximo trimestre": "proximo_trimestre",
    "trimestre": "proximo_trimestre",
    "90_dias": "proximo_trimestre",
}


def normalize_horizonte(value: str) -> HorizonteEstimacionLiteral:
    cleaned = " ".join(str(value or "").strip().lower().split())
    mapped = _HORIZONTE_ALIASES.get(cleaned)
    if mapped is None:
        raise ValueError(
            "El horizonte de estimación debe ser 'proxima_semana', 'proximo_mes' o 'proximo_trimestre'."
        )
    return mapped


class DemandForecastRequest(BaseModel):
    producto_id: int | None = Field(default=None, gt=0)
    producto_nombre: str | None = Field(default=None, max_length=100)
    fecha_desde: date
    fecha_hasta: date
    horizonte: HorizonteEstimacionLiteral = "proxima_semana"
    incluir_sinteticos: bool = True
    fecha_referencia: date | None = None
    sobrante_disponible_inicial: int | None = Field(default=None, ge=0)

    @field_validator("producto_nombre")
    @classmethod
    def validate_producto_nombre(cls, value: str | None) -> str | None:
        return normalize_optional_str(value)

    @field_validator("horizonte", mode="before")
    @classmethod
    def validate_horizonte(cls, value: object) -> HorizonteEstimacionLiteral:
        if not isinstance(value, str):
            raise ValueError("El horizonte de estimación no es válido.")
        return normalize_horizonte(value)

    @model_validator(mode="after")
    def validate_request_rules(self) -> DemandForecastRequest:
        if self.producto_id is None and not self.producto_nombre:
            raise ValueError(
                "Debe indicar producto_id o producto_nombre para generar la estimación."
            )
        if self.fecha_desde > self.fecha_hasta:
            raise ValueError(
                "La fecha inicial del período histórico no puede ser posterior a la fecha final."
            )
        return self


class PerfilTipoDiaResponse(BaseModel):
    tipo_dia: TipoDiaOperativoLiteral
    etiqueta: str
    dias_observados: int
    promedio_simple_base: Decimal
    promedio_ponderado_base: Decimal
    minimo_observado_base: Decimal
    maximo_observado_base: Decimal


class ResumenHistoricoDemanda(BaseModel):
    fecha_desde: date
    fecha_hasta: date
    fecha_minima_observada: date
    fecha_maxima_observada: date
    total_dias_calendario_rango: int
    dias_operativos_calendario_rango: int
    dias_operativos_con_ventas: int
    dias_operativos_sin_ventas: int
    fechas_no_operativas_excluidas: list[date] = Field(default_factory=list)
    registros_reales: int
    registros_sinteticos: int
    registros_operativos: int
    proporcion_datos_reales: Decimal
    total_vendido_base: Decimal
    promedio_diario_simple_base: Decimal
    promedio_diario_ponderado_base: Decimal
    desviacion_estandar_base: Decimal
    tendencia_porcentual_aplicada: Decimal
    promedio_sobrante_historico_base: Decimal
    ultimo_sobrante_registrado_base: Decimal
    fecha_ultimo_cierre: date | None = None
    perfiles_por_tipo_dia: list[PerfilTipoDiaResponse] = Field(default_factory=list)


class MetricasPrecisionModelo(BaseModel):
    metodo: str
    origen_evaluacion: OrigenEvaluacionLiteral
    muestras_evaluadas: int
    mae_base: Decimal | None = None
    rmse_base: Decimal | None = None
    mape_porcentaje: Decimal | None = None
    precision_estimada_porcentaje: Decimal | None = None
    nivel_confianza: NivelConfianzaLiteral
    nota_metodologica: str


class DiaPlanificacionDemanda(BaseModel):
    fecha: date
    dia_semana: str
    etiqueta_dia: str
    tipo_dia: TipoDiaOperativoLiteral
    es_sabado: bool
    es_domingo: bool
    es_festivo_nacional: bool
    nombre_festivo: str | None = None
    producto_id: int
    producto_nombre: str
    unidad_base: str
    demanda_base_tipo_dia: Decimal
    factor_ajuste_aplicado: Decimal
    demanda_estimada: int
    sobrantes_disponibles: int
    produccion_sugerida: int
    rango_minimo_esperado: int
    rango_maximo_esperado: int
    explicacion_dia: str


class RecomendacionDemanda(BaseModel):
    tipo: Literal["produccion", "calendario", "sobrantes", "datos", "precision"]
    titulo: str
    detalle: str


class DemandForecastResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    producto_id: int
    producto_nombre: str
    unidad_base: str
    horizonte: HorizonteEstimacionLiteral
    horizonte_etiqueta: str
    fecha_inicio_horizonte: date
    fecha_fin_horizonte: date
    total_dias_operativos_proyectados: int
    demanda_total_estimada: int
    sobrantes_totales_disponibles: int
    produccion_total_sugerida: int
    incluir_sinteticos: bool
    resumen_historico: ResumenHistoricoDemanda
    metricas_precision: MetricasPrecisionModelo
    planificacion_diaria: list[DiaPlanificacionDemanda]
    recomendaciones: list[RecomendacionDemanda]
    generado_en: datetime


class ProductoContextoDemanda(BaseModel):
    producto_id: int
    producto_nombre: str
    unidad_base: str
    fecha_minima_ventas: date | None = None
    fecha_maxima_ventas: date | None = None
    fecha_minima_reales: date | None = None
    fecha_maxima_reales: date | None = None
    dias_operativos_totales: int
    dias_reales: int
    dias_sinteticos: int
    dias_operativos_app: int
    ultimo_sobrante_real_base: int
    fecha_ultimo_cierre: date | None = None


class DemandHistoricalContextResponse(BaseModel):
    fecha_minima_global: date | None = None
    fecha_maxima_global: date | None = None
    fecha_inicio_datos_reales: date | None = None
    fecha_maxima_datos_reales: date | None = None
    minimo_dias_operativos_requeridos: int
    dias_operativos_recomendados: int
    productos: list[ProductoContextoDemanda]
