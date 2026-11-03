from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _strip_required(value: str, field_label: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise ValueError(f"{field_label} no puede estar vacío.")
    return cleaned


def _strip_optional(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


class PresentacionBase(BaseModel):
    nombre: str = Field(..., min_length=1, max_length=100)
    unidad_venta: str = Field(..., min_length=1, max_length=30)
    factor_conversion: Decimal = Field(..., gt=Decimal("0"))
    precio_actual: Decimal = Field(default=Decimal("0.00"), ge=Decimal("0"))
    activo: bool = True

    @field_validator("nombre")
    @classmethod
    def validate_nombre(cls, value: str) -> str:
        return _strip_required(value, "El nombre de la presentación")

    @field_validator("unidad_venta")
    @classmethod
    def validate_unidad_venta(cls, value: str) -> str:
        return _strip_required(value, "La unidad de venta")


class PresentacionCreate(PresentacionBase):
    producto_id: int = Field(..., gt=0)


class PresentacionUpdate(BaseModel):
    nombre: str | None = Field(default=None, min_length=1, max_length=100)
    unidad_venta: str | None = Field(default=None, min_length=1, max_length=30)
    factor_conversion: Decimal | None = Field(default=None, gt=Decimal("0"))
    precio_actual: Decimal | None = Field(default=None, ge=Decimal("0"))
    activo: bool | None = None

    @field_validator("nombre")
    @classmethod
    def validate_nombre(cls, value: str | None) -> str | None:
        return (
            _strip_required(value, "El nombre de la presentación")
            if value is not None
            else None
        )

    @field_validator("unidad_venta")
    @classmethod
    def validate_unidad_venta(cls, value: str | None) -> str | None:
        return (
            _strip_required(value, "La unidad de venta")
            if value is not None
            else None
        )


class PresentacionResponse(PresentacionBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    producto_id: int
    creado_en: datetime
    actualizado_en: datetime


class ProductoBase(BaseModel):
    nombre: str = Field(..., min_length=1, max_length=100)
    descripcion: str | None = Field(default=None, max_length=500)
    unidad_base: str = Field(..., min_length=1, max_length=30)
    activo: bool = True

    @field_validator("nombre")
    @classmethod
    def validate_nombre(cls, value: str) -> str:
        return _strip_required(value, "El nombre del producto")

    @field_validator("unidad_base")
    @classmethod
    def validate_unidad_base(cls, value: str) -> str:
        return _strip_required(value, "La unidad base")

    @field_validator("descripcion")
    @classmethod
    def validate_descripcion(cls, value: str | None) -> str | None:
        return _strip_optional(value)


class ProductoCreate(ProductoBase):
    pass


class ProductoUpdate(BaseModel):
    nombre: str | None = Field(default=None, min_length=1, max_length=100)
    descripcion: str | None = Field(default=None, max_length=500)
    unidad_base: str | None = Field(default=None, min_length=1, max_length=30)
    activo: bool | None = None

    @field_validator("nombre")
    @classmethod
    def validate_nombre(cls, value: str | None) -> str | None:
        return (
            _strip_required(value, "El nombre del producto")
            if value is not None
            else None
        )

    @field_validator("unidad_base")
    @classmethod
    def validate_unidad_base(cls, value: str | None) -> str | None:
        return (
            _strip_required(value, "La unidad base")
            if value is not None
            else None
        )

    @field_validator("descripcion")
    @classmethod
    def validate_descripcion(cls, value: str | None) -> str | None:
        return _strip_optional(value)


class ProductoResponse(ProductoBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    creado_en: datetime
    actualizado_en: datetime
    presentaciones: list[PresentacionResponse] = Field(default_factory=list)


class CatalogSeedWarning(BaseModel):
    entidad: Literal["producto", "presentacion"]
    nombre: str
    campo: str
    valor_actual: str
    valor_esperado: str
    mensaje: str


class CatalogSeedResult(BaseModel):
    productos_creados: list[str] = Field(default_factory=list)
    productos_existentes: list[str] = Field(default_factory=list)
    presentaciones_creadas: list[str] = Field(default_factory=list)
    presentaciones_existentes: list[str] = Field(default_factory=list)
    revisiones_manuales: list[CatalogSeedWarning] = Field(default_factory=list)
