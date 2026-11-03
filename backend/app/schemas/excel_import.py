from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field


class ExcelValidationIssue(BaseModel):
    severidad: Literal["warning", "error"]
    hoja: str
    fila: int | None = None
    codigo: str
    mensaje: str


class ExcelSheetSummary(BaseModel):
    hoja: str
    filas_totales_con_encabezado: int
    filas_vacias_ignoradas: int
    registros_validos: int
    registros_reales: int
    registros_sinteticos: int


class ExcelAuditReport(BaseModel):
    archivo: str
    valido_para_importar: bool
    fecha_corte_real: date
    fecha_minima_operacion: date | None = None
    fecha_maxima_operacion: date | None = None
    total_fechas_operacion: int = 0
    total_clientes_unicos: int = 0
    clientes_reales: int = 0
    clientes_sinteticos: int = 0
    total_ventas_cop: Decimal = Decimal("0.00")
    total_ventas_reales_cop: Decimal = Decimal("0.00")
    total_ventas_sinteticas_cop: Decimal = Decimal("0.00")
    hojas: list[ExcelSheetSummary] = Field(default_factory=list)
    advertencias: list[ExcelValidationIssue] = Field(default_factory=list)
    errores: list[ExcelValidationIssue] = Field(default_factory=list)


class TableImportCounter(BaseModel):
    creados: int = 0
    existentes: int = 0
    reales_creados: int = 0
    sinteticos_creados: int = 0


class ExcelImportResult(BaseModel):
    archivo: str
    dry_run: bool
    fecha_corte_real: date
    tablas: dict[str, TableImportCounter] = Field(default_factory=dict)
    advertencias: list[ExcelValidationIssue] = Field(default_factory=list)
