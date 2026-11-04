from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.customers import OrigenRegistroLiteral, normalize_optional_str


def _coerce_datetime(value: datetime | date | str | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day, 0, 0, 0)
    if isinstance(value, str):
        cleaned = value.strip()
        if len(cleaned) == 10 and cleaned[4] == "-" and cleaned[7] == "-":
            parsed_date = date.fromisoformat(cleaned)
            return datetime(
                parsed_date.year, parsed_date.month, parsed_date.day, 0, 0, 0
            )
        return datetime.fromisoformat(cleaned)
    raise ValueError("Formato de fecha de producción inválido.")


class ProduccionCreate(BaseModel):
    producto_id: int | None = Field(default=None, gt=0)
    producto_nombre: str | None = Field(default=None, max_length=100)
    fecha_produccion: datetime | None = None
    cantidad_producida_base: Decimal = Field(..., gt=Decimal("0"))
    sobrante_real_base: Decimal = Field(default=Decimal("0"), ge=Decimal("0"))
    observaciones: str | None = Field(default=None, max_length=1000)

    @field_validator("producto_nombre")
    @classmethod
    def validate_producto_nombre(cls, value: str | None) -> str | None:
        return normalize_optional_str(value)

    @field_validator("fecha_produccion", mode="before")
    @classmethod
    def validate_fecha_produccion(cls, value: object) -> datetime | None:
        if value is None:
            return None
        return _coerce_datetime(value)  # type: ignore[arg-type]

    @field_validator("cantidad_producida_base")
    @classmethod
    def validate_cantidad_producida_entera(cls, value: Decimal) -> Decimal:
        if value <= 0 or value != int(value):
            raise ValueError(
                "La cantidad producida debe ser un número entero mayor que cero en su unidad base (Unidad o Plato)."
            )
        return Decimal(int(value))

    @field_validator("sobrante_real_base")
    @classmethod
    def validate_sobrante_entero(cls, value: Decimal) -> Decimal:
        if value < 0 or value != int(value):
            raise ValueError(
                "Los sobrantes registrados deben ser cero o un número entero positivo."
            )
        return Decimal(int(value))

    @field_validator("observaciones")
    @classmethod
    def validate_observaciones(cls, value: str | None) -> str | None:
        cleaned = normalize_optional_str(value)
        if cleaned is not None and "IMPORTACION_EXCEL|" in cleaned:
            raise ValueError(
                "La marca IMPORTACION_EXCEL está reservada para la trazabilidad histórica."
            )
        return cleaned

    @model_validator(mode="after")
    def validate_production_rules(self) -> ProduccionCreate:
        if self.producto_id is None and not self.producto_nombre:
            raise ValueError(
                "Debe indicar producto_id o producto_nombre para registrar la producción."
            )
        if self.sobrante_real_base > self.cantidad_producida_base:
            raise ValueError(
                "Los sobrantes registrados no pueden superar la cantidad producida."
            )
        return self


class ProduccionUpdate(BaseModel):
    fecha_produccion: datetime | None = None
    cantidad_producida_base: Decimal | None = Field(default=None, gt=Decimal("0"))
    sobrante_real_base: Decimal | None = Field(default=None, ge=Decimal("0"))
    observaciones: str | None = Field(default=None, max_length=1000)

    @field_validator("fecha_produccion", mode="before")
    @classmethod
    def validate_fecha_produccion(cls, value: object) -> datetime | None:
        if value is None:
            return None
        return _coerce_datetime(value)  # type: ignore[arg-type]

    @field_validator("cantidad_producida_base")
    @classmethod
    def validate_cantidad_producida_entera(
        cls, value: Decimal | None
    ) -> Decimal | None:
        if value is None:
            return None
        if value <= 0 or value != int(value):
            raise ValueError(
                "La cantidad producida debe ser un número entero mayor que cero en su unidad base (Unidad o Plato)."
            )
        return Decimal(int(value))

    @field_validator("sobrante_real_base")
    @classmethod
    def validate_sobrante_entero(cls, value: Decimal | None) -> Decimal | None:
        if value is None:
            return None
        if value < 0 or value != int(value):
            raise ValueError(
                "Los sobrantes registrados deben ser cero o un número entero positivo."
            )
        return Decimal(int(value))

    @field_validator("observaciones")
    @classmethod
    def validate_observaciones(cls, value: str | None) -> str | None:
        cleaned = normalize_optional_str(value)
        if cleaned is not None and "IMPORTACION_EXCEL|" in cleaned:
            raise ValueError(
                "La marca IMPORTACION_EXCEL está reservada para la trazabilidad histórica."
            )
        return cleaned

    @model_validator(mode="after")
    def validate_update_bounds(self) -> ProduccionUpdate:
        if (
            self.cantidad_producida_base is not None
            and self.sobrante_real_base is not None
            and self.sobrante_real_base > self.cantidad_producida_base
        ):
            raise ValueError(
                "Los sobrantes registrados no pueden superar la cantidad producida."
            )
        return self


class ProduccionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    producto_id: int
    producto_nombre: str
    unidad_base: str
    fecha_produccion: datetime
    fecha_jornada: date
    cantidad_producida_base: Decimal
    cantidad_vendida_fecha: Decimal
    existencia_calculada_base: Decimal
    sobrante_real_base: Decimal
    diferencia_base: Decimal
    observaciones: str | None
    es_historico: bool
    es_sintetico: bool
    origen_registro: OrigenRegistroLiteral
    creado_en: datetime
