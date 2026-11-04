from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class LoginRequest(BaseModel):
    nombre_usuario: str = Field(..., min_length=1, max_length=80)
    password: str = Field(..., min_length=1, max_length=256)

    @field_validator("nombre_usuario")
    @classmethod
    def validate_nombre_usuario(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("El nombre de usuario no puede estar vacío.")
        return cleaned

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        if not value:
            raise ValueError("La contraseña no puede estar vacía.")
        return value


class UsuarioPublicResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    nombre_usuario: str
    nombre_completo: str
    activo: bool
    ultimo_acceso: datetime | None
    creado_en: datetime
    actualizado_en: datetime


class TokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int
    usuario: UsuarioPublicResponse


class AdminInitResult(BaseModel):
    creado: bool
    usuario: UsuarioPublicResponse
    mensaje: str
