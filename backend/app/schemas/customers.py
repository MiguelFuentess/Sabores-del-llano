from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

OrigenRegistroLiteral = Literal["operativo", "historico_real", "historico_sintetico"]


def normalize_person_name(value: str) -> str:
    cleaned = " ".join(value.strip().split())
    if not cleaned:
        raise ValueError("El nombre del cliente no puede estar vacío.")
    return cleaned


def normalize_optional_str(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def normalize_phone(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = " ".join(value.strip().split())
    return cleaned or None


class ClienteBase(BaseModel):
    nombre: str = Field(..., min_length=1, max_length=120)
    telefono: str | None = Field(default=None, max_length=30)
    correo: str | None = Field(default=None, max_length=150)
    notas: str | None = Field(default=None, max_length=500)
    activo: bool = True

    @field_validator("nombre")
    @classmethod
    def validate_nombre(cls, value: str) -> str:
        return normalize_person_name(value)

    @field_validator("telefono")
    @classmethod
    def validate_telefono(cls, value: str | None) -> str | None:
        return normalize_phone(value)

    @field_validator("correo")
    @classmethod
    def validate_correo(cls, value: str | None) -> str | None:
        cleaned = normalize_optional_str(value)
        if cleaned is not None and "@" not in cleaned:
            raise ValueError("El correo electrónico no tiene un formato válido.")
        return cleaned

    @field_validator("notas")
    @classmethod
    def validate_notas(cls, value: str | None) -> str | None:
        cleaned = normalize_optional_str(value)
        if cleaned is not None and "IMPORTACION_EXCEL|" in cleaned:
            raise ValueError(
                "La marca IMPORTACION_EXCEL está reservada para la trazabilidad histórica."
            )
        return cleaned


class ClienteCreate(ClienteBase):
    permitir_homonimo: bool = Field(
        default=False,
        description=(
            "Si es True, permite registrar un nuevo cliente aunque exista otro "
            "con el mismo nombre sin datos de contacto diferenciadores."
        ),
    )


class ClienteUpdate(BaseModel):
    nombre: str | None = Field(default=None, min_length=1, max_length=120)
    telefono: str | None = Field(default=None, max_length=30)
    correo: str | None = Field(default=None, max_length=150)
    notas: str | None = Field(default=None, max_length=500)
    activo: bool | None = None

    @field_validator("nombre")
    @classmethod
    def validate_nombre(cls, value: str | None) -> str | None:
        return normalize_person_name(value) if value is not None else None

    @field_validator("telefono")
    @classmethod
    def validate_telefono(cls, value: str | None) -> str | None:
        return normalize_phone(value)

    @field_validator("correo")
    @classmethod
    def validate_correo(cls, value: str | None) -> str | None:
        cleaned = normalize_optional_str(value)
        if cleaned is not None and "@" not in cleaned:
            raise ValueError("El correo electrónico no tiene un formato válido.")
        return cleaned

    @field_validator("notas")
    @classmethod
    def validate_notas(cls, value: str | None) -> str | None:
        cleaned = normalize_optional_str(value)
        if cleaned is not None and "IMPORTACION_EXCEL|" in cleaned:
            raise ValueError(
                "La marca IMPORTACION_EXCEL está reservada para la trazabilidad histórica."
            )
        return cleaned


class ClienteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    nombre: str
    telefono: str | None
    correo: str | None
    notas: str | None
    activo: bool
    es_historico: bool
    es_sintetico: bool
    origen_registro: OrigenRegistroLiteral
    creado_en: datetime
    actualizado_en: datetime
