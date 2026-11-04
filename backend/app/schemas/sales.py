from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.customers import OrigenRegistroLiteral, normalize_optional_str

VentaEstadoLiteral = Literal["concretada", "anulada"]


class DetalleVentaItemInput(BaseModel):
    presentacion_id: int | None = Field(default=None, gt=0)
    producto_id: int | None = Field(default=None, gt=0)
    producto_nombre: str | None = Field(default=None, max_length=100)
    cantidad: Decimal = Field(..., gt=Decimal("0"))
    precio_unitario: Decimal | None = Field(default=None, gt=Decimal("0"))

    @field_validator("producto_nombre")
    @classmethod
    def validate_producto_nombre(cls, value: str | None) -> str | None:
        return normalize_optional_str(value)

    @field_validator("cantidad")
    @classmethod
    def validate_cantidad_entera(cls, value: Decimal) -> Decimal:
        if value <= 0 or value != int(value):
            raise ValueError(
                "La cantidad vendida debe ser un número entero mayor que cero en su unidad base (Unidad o Plato)."
            )
        return Decimal(int(value))

    @field_validator("precio_unitario")
    @classmethod
    def validate_precio_unitario(cls, value: Decimal | None) -> Decimal | None:
        if value is None:
            return None
        if value <= 0:
            raise ValueError("El precio unitario debe ser mayor que cero.")
        return value.quantize(Decimal("0.01"))

    @model_validator(mode="after")
    def validate_product_reference(self) -> DetalleVentaItemInput:
        if (
            self.presentacion_id is None
            and self.producto_id is None
            and not self.producto_nombre
        ):
            raise ValueError(
                "Debe indicar presentacion_id, producto_id o producto_nombre para cada detalle de la venta."
            )
        return self


class DetalleVentaResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    venta_id: int
    presentacion_id: int
    producto_id: int
    producto_nombre: str
    presentacion_nombre: str
    unidad_base: str
    unidad_venta: str
    cantidad: Decimal
    precio_unitario: Decimal
    factor_conversion_snapshot: Decimal
    cantidad_base: Decimal
    subtotal: Decimal


class VentaCreate(BaseModel):
    pedido_id: int | None = Field(default=None, gt=0)
    fecha_venta: datetime | None = None
    estado: VentaEstadoLiteral = "concretada"
    observaciones: str | None = Field(default=None, max_length=1000)
    detalles: list[DetalleVentaItemInput] = Field(..., min_length=1)

    @field_validator("observaciones")
    @classmethod
    def validate_observaciones(cls, value: str | None) -> str | None:
        cleaned = normalize_optional_str(value)
        if cleaned is not None and "IMPORTACION_EXCEL|" in cleaned:
            raise ValueError(
                "La marca IMPORTACION_EXCEL está reservada para la trazabilidad histórica."
            )
        return cleaned


class VentaUpdate(BaseModel):
    fecha_venta: datetime | None = None
    estado: VentaEstadoLiteral | None = None
    observaciones: str | None = Field(default=None, max_length=1000)
    detalles: list[DetalleVentaItemInput] | None = Field(default=None, min_length=1)

    @field_validator("observaciones")
    @classmethod
    def validate_observaciones(cls, value: str | None) -> str | None:
        cleaned = normalize_optional_str(value)
        if cleaned is not None and "IMPORTACION_EXCEL|" in cleaned:
            raise ValueError(
                "La marca IMPORTACION_EXCEL está reservada para la trazabilidad histórica."
            )
        return cleaned


class VentaResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    pedido_id: int | None
    fecha_venta: datetime
    estado: VentaEstadoLiteral
    observaciones: str | None
    es_historico: bool
    es_sintetico: bool
    origen_registro: OrigenRegistroLiteral
    cantidad_total_base: Decimal
    total: Decimal
    detalles: list[DetalleVentaResponse]
    creado_en: datetime
