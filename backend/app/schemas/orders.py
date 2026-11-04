from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.customers import (
    OrigenRegistroLiteral,
    normalize_optional_str,
    normalize_person_name,
    normalize_phone,
)

PedidoEstadoLiteral = Literal[
    "pendiente",
    "confirmado",
    "en_preparacion",
    "entregado",
    "cancelado",
]
ModalidadEntregaLiteral = Literal["retiro", "domicilio"]


class DetallePedidoItemInput(BaseModel):
    presentacion_id: int | None = Field(default=None, gt=0)
    producto_id: int | None = Field(default=None, gt=0)
    producto_nombre: str | None = Field(default=None, max_length=100)
    cantidad: Decimal = Field(..., gt=Decimal("0"))
    observaciones: str | None = Field(default=None, max_length=500)

    @field_validator("producto_nombre")
    @classmethod
    def validate_producto_nombre(cls, value: str | None) -> str | None:
        return normalize_optional_str(value)

    @field_validator("cantidad")
    @classmethod
    def validate_cantidad_entera(cls, value: Decimal) -> Decimal:
        if value <= 0 or value != int(value):
            raise ValueError(
                "La cantidad debe ser un número entero mayor que cero en su unidad base (Unidad o Plato)."
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
    def validate_product_reference(self) -> DetallePedidoItemInput:
        if (
            self.presentacion_id is None
            and self.producto_id is None
            and not self.producto_nombre
        ):
            raise ValueError(
                "Debe indicar presentacion_id, producto_id o producto_nombre para cada detalle del pedido."
            )
        return self


class DetallePedidoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    pedido_id: int
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
    observaciones: str | None


class PedidoCreate(BaseModel):
    cliente_nombre: str | None = Field(
        default=None,
        max_length=120,
        description="Nombre del cliente ingresado como texto libre.",
    )
    cliente_id: int | None = Field(default=None, gt=0)
    forzar_nuevo_cliente: bool = Field(
        default=False,
        description=(
            "Si es True, crea un nuevo registro de cliente aunque exista uno con el mismo nombre."
        ),
    )
    fecha_pedido: datetime | None = None
    fecha_entrega_prevista: datetime
    estado: PedidoEstadoLiteral = "pendiente"
    modalidad_entrega: ModalidadEntregaLiteral = "retiro"
    nombre_contacto: str | None = Field(default=None, max_length=120)
    telefono_contacto: str | None = Field(default=None, max_length=30)
    direccion_entrega: str | None = Field(default=None, max_length=255)
    observaciones: str | None = Field(default=None, max_length=1000)
    detalles: list[DetallePedidoItemInput] = Field(..., min_length=1)

    @field_validator("cliente_nombre")
    @classmethod
    def validate_cliente_nombre(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return normalize_person_name(value)

    @field_validator("nombre_contacto")
    @classmethod
    def validate_nombre_contacto(cls, value: str | None) -> str | None:
        return normalize_optional_str(value)

    @field_validator("telefono_contacto")
    @classmethod
    def validate_telefono_contacto(cls, value: str | None) -> str | None:
        return normalize_phone(value)

    @field_validator("direccion_entrega")
    @classmethod
    def validate_direccion_entrega(cls, value: str | None) -> str | None:
        return normalize_optional_str(value)

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
    def validate_order_business_rules(self) -> PedidoCreate:
        if not self.cliente_nombre and self.cliente_id is None:
            raise ValueError(
                "Debe proporcionar el nombre del cliente (texto libre) o un cliente_id válido."
            )
        if (
            self.fecha_pedido is not None
            and self.fecha_entrega_prevista.date() < self.fecha_pedido.date()
        ):
            raise ValueError(
                "La fecha de entrega prevista no puede ser anterior a la fecha del pedido."
            )
        if self.modalidad_entrega == "domicilio":
            if not self.direccion_entrega:
                raise ValueError(
                    "La dirección de entrega es obligatoria cuando la modalidad es domicilio."
                )
            if not self.telefono_contacto:
                raise ValueError(
                    "El teléfono de contacto es obligatorio cuando la modalidad es domicilio."
                )
        else:
            self.direccion_entrega = None
        return self


class PedidoUpdate(BaseModel):
    fecha_entrega_prevista: datetime | None = None
    estado: PedidoEstadoLiteral | None = None
    modalidad_entrega: ModalidadEntregaLiteral | None = None
    nombre_contacto: str | None = Field(default=None, max_length=120)
    telefono_contacto: str | None = Field(default=None, max_length=30)
    direccion_entrega: str | None = Field(default=None, max_length=255)
    observaciones: str | None = Field(default=None, max_length=1000)
    detalles: list[DetallePedidoItemInput] | None = Field(default=None, min_length=1)

    @field_validator("nombre_contacto")
    @classmethod
    def validate_nombre_contacto(cls, value: str | None) -> str | None:
        return normalize_optional_str(value)

    @field_validator("telefono_contacto")
    @classmethod
    def validate_telefono_contacto(cls, value: str | None) -> str | None:
        return normalize_phone(value)

    @field_validator("direccion_entrega")
    @classmethod
    def validate_direccion_entrega(cls, value: str | None) -> str | None:
        return normalize_optional_str(value)

    @field_validator("observaciones")
    @classmethod
    def validate_observaciones(cls, value: str | None) -> str | None:
        cleaned = normalize_optional_str(value)
        if cleaned is not None and "IMPORTACION_EXCEL|" in cleaned:
            raise ValueError(
                "La marca IMPORTACION_EXCEL está reservada para la trazabilidad histórica."
            )
        return cleaned


class PedidoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    cliente_id: int | None
    cliente_nombre: str | None
    fecha_pedido: datetime
    fecha_entrega_prevista: datetime | None
    estado: PedidoEstadoLiteral
    modalidad_entrega: ModalidadEntregaLiteral
    nombre_contacto: str | None
    telefono_contacto: str | None
    direccion_entrega: str | None
    observaciones: str | None
    es_historico: bool
    es_sintetico: bool
    origen_registro: OrigenRegistroLiteral
    cantidad_total_base: Decimal
    total: Decimal
    detalles: list[DetallePedidoResponse]
    creado_en: datetime
    actualizado_en: datetime
