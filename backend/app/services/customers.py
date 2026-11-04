from __future__ import annotations

import re

from fastapi import HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models import Cliente
from app.schemas.customers import (
    ClienteCreate,
    ClienteResponse,
    ClienteUpdate,
    OrigenRegistroLiteral,
    normalize_person_name,
    normalize_phone,
)
from app.services.excel_import import is_synthetic_trace

_TRACE_TAG_PATTERN = re.compile(r"\[IMPORTACION_EXCEL\|[^\]]+\]")


def classify_trace_origin(
    text_field: str | None,
) -> tuple[bool, bool, OrigenRegistroLiteral]:
    """Determina si un registro proviene de la importación histórica (real o sintético) o es operativo."""
    syn = is_synthetic_trace(text_field)
    if syn is True:
        return True, True, "historico_sintetico"
    if syn is False:
        return True, False, "historico_real"
    return False, False, "operativo"


def extract_trace_tag(text_field: str | None) -> str | None:
    if not text_field:
        return None
    match = _TRACE_TAG_PATTERN.search(text_field)
    return match.group(0) if match else None


def serialize_cliente(cliente: Cliente) -> ClienteResponse:
    es_historico, es_sintetico, origen = classify_trace_origin(cliente.notas)
    return ClienteResponse(
        id=cliente.id,
        nombre=cliente.nombre,
        telefono=cliente.telefono,
        correo=cliente.correo,
        notas=cliente.notas,
        activo=bool(cliente.activo),
        es_historico=es_historico,
        es_sintetico=es_sintetico,
        origen_registro=origen,
        creado_en=cliente.creado_en,
        actualizado_en=cliente.actualizado_en,
    )


def get_cliente_or_404(session: Session, cliente_id: int) -> Cliente:
    cliente = session.get(Cliente, cliente_id)
    if cliente is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"El cliente con id {cliente_id} no existe.",
        )
    return cliente


def list_clientes(
    session: Session,
    *,
    q: str | None = None,
    solo_activos: bool = False,
    incluir_sinteticos: bool = True,
    solo_operativos: bool = False,
    limit: int = 500,
    offset: int = 0,
) -> list[ClienteResponse]:
    stmt = select(Cliente).order_by(Cliente.id.desc())

    if solo_activos:
        stmt = stmt.where(Cliente.activo.is_(True))

    if q and q.strip():
        pattern = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                Cliente.nombre.ilike(pattern),
                Cliente.telefono.ilike(pattern),
                Cliente.correo.ilike(pattern),
            )
        )

    if solo_operativos:
        stmt = stmt.where(
            or_(
                Cliente.notas.is_(None),
                ~Cliente.notas.like("%IMPORTACION_EXCEL|%"),
            )
        )
    elif not incluir_sinteticos:
        stmt = stmt.where(
            or_(
                Cliente.notas.is_(None),
                ~Cliente.notas.like("%|es_sintetico=1%"),
            )
        )

    stmt = stmt.offset(offset).limit(limit)
    clientes = session.scalars(stmt).all()
    return [serialize_cliente(c) for c in clientes]


def create_cliente(
    session: Session,
    payload: ClienteCreate,
    *,
    commit: bool = True,
) -> ClienteResponse:
    existing_same_name = list(
        session.scalars(
            select(Cliente).where(
                func.lower(Cliente.nombre) == payload.nombre.lower()
            )
        ).all()
    )
    non_synthetic_matches = [
        c for c in existing_same_name if is_synthetic_trace(c.notas) is not True
    ]

    for existing in non_synthetic_matches:
        # Si ambos tienen el mismo teléfono no nulo, es el mismo cliente duplicado
        if (
            payload.telefono
            and existing.telefono
            and existing.telefono == payload.telefono
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Ya existe un cliente registrado con el nombre '{payload.nombre}' "
                    f"y el teléfono '{payload.telefono}' (id={existing.id})."
                ),
            )
        # Si ambos tienen el mismo correo no nulo, es el mismo cliente duplicado
        if (
            payload.correo
            and existing.correo
            and existing.correo.lower() == payload.correo.lower()
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Ya existe un cliente registrado con el nombre '{payload.nombre}' "
                    f"y el correo '{payload.correo}' (id={existing.id})."
                ),
            )

        # Si tienen teléfonos o correos distintos (ambos no nulos), se trata de un homónimo legítimo
        has_distinct_phone = bool(
            payload.telefono
            and existing.telefono
            and payload.telefono != existing.telefono
        )
        has_distinct_email = bool(
            payload.correo
            and existing.correo
            and payload.correo.lower() != existing.correo.lower()
        )
        if has_distinct_phone or has_distinct_email or payload.permitir_homonimo:
            continue

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Ya existe un cliente llamado '{payload.nombre}' (id={existing.id}). "
                "Para evitar duplicados sin mezclar homónimos, indique un teléfono o correo "
                "diferenciador o active permitir_homonimo=true si es otra persona."
            ),
        )

    cliente = Cliente(
        nombre=payload.nombre,
        telefono=payload.telefono,
        correo=payload.correo,
        notas=payload.notas,
        activo=payload.activo,
    )
    session.add(cliente)
    if commit:
        session.commit()
        session.refresh(cliente)
    else:
        session.flush()
    return serialize_cliente(cliente)


def update_cliente(
    session: Session,
    cliente_id: int,
    payload: ClienteUpdate,
    *,
    commit: bool = True,
) -> ClienteResponse:
    cliente = get_cliente_or_404(session, cliente_id)
    es_historico, _, _ = classify_trace_origin(cliente.notas)
    trace_tag = extract_trace_tag(cliente.notas)

    updates = payload.model_dump(exclude_unset=True)

    if (
        es_historico
        and "nombre" in updates
        and updates["nombre"] is not None
        and updates["nombre"].lower() != cliente.nombre.lower()
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No se permite modificar el nombre de un cliente histórico importado.",
        )

    target_name = updates.get("nombre") or cliente.nombre
    target_phone = updates.get("telefono", cliente.telefono)

    if "nombre" in updates or "telefono" in updates:
        other_matches = list(
            session.scalars(
                select(Cliente).where(
                    func.lower(Cliente.nombre) == target_name.lower(),
                    Cliente.id != cliente.id,
                )
            ).all()
        )
        for other in other_matches:
            if is_synthetic_trace(other.notas) is True:
                continue
            if target_phone and other.telefono and other.telefono == target_phone:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        f"Ya existe otro cliente con el nombre '{target_name}' "
                        f"y el teléfono '{target_phone}' (id={other.id})."
                    ),
                )

    if "nombre" in updates and updates["nombre"] is not None:
        cliente.nombre = updates["nombre"]
    if "telefono" in updates:
        cliente.telefono = updates["telefono"]
    if "correo" in updates:
        cliente.correo = updates["correo"]
    if "activo" in updates and updates["activo"] is not None:
        cliente.activo = updates["activo"]
    if "notas" in updates:
        new_notes = updates["notas"]
        if trace_tag:
            cliente.notas = f"{trace_tag} {new_notes}".strip() if new_notes else trace_tag
        else:
            cliente.notas = new_notes

    if commit:
        session.commit()
        session.refresh(cliente)
    else:
        session.flush()
    return serialize_cliente(cliente)


def resolve_or_create_cliente_for_order(
    session: Session,
    *,
    cliente_id: int | None = None,
    cliente_nombre: str | None = None,
    telefono_contacto: str | None = None,
    forzar_nuevo_cliente: bool = False,
) -> Cliente:
    """Resuelve de forma controlada si corresponde asociar un cliente existente o crear uno nuevo
    a partir del nombre en texto libre, evitando duplicados sin fusionar homónimos."""
    cleaned_phone = normalize_phone(telefono_contacto)

    if cliente_id is not None:
        cliente = get_cliente_or_404(session, cliente_id)
        if not cliente.activo:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"El cliente con id {cliente_id} está inactivo.",
            )
        if cliente_nombre:
            cleaned_name = normalize_person_name(cliente_nombre)
            if cliente.nombre.lower() != cleaned_name.lower():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        f"El cliente_id {cliente_id} pertenece a '{cliente.nombre}' "
                        f"y no coincide con '{cleaned_name}'."
                    ),
                )
        return cliente

    if not cliente_nombre:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Debe indicar el nombre del cliente o su identificador.",
        )

    cleaned_name = normalize_person_name(cliente_nombre)

    if forzar_nuevo_cliente:
        nuevo = Cliente(nombre=cleaned_name, telefono=cleaned_phone, activo=True)
        session.add(nuevo)
        session.flush()
        return nuevo

    matches = list(
        session.scalars(
            select(Cliente)
            .where(
                func.lower(Cliente.nombre) == cleaned_name.lower(),
                Cliente.activo.is_(True),
            )
            .order_by(Cliente.id.asc())
        ).all()
    )
    # Nunca fusionar un pedido operativo nuevo con un cliente sintético histórico
    candidatos = [c for c in matches if is_synthetic_trace(c.notas) is not True]

    if not candidatos:
        nuevo = Cliente(nombre=cleaned_name, telefono=cleaned_phone, activo=True)
        session.add(nuevo)
        session.flush()
        return nuevo

    if cleaned_phone:
        # 1. Coincidencia exacta de nombre + teléfono -> es la misma persona
        for cand in candidatos:
            if cand.telefono and cand.telefono == cleaned_phone:
                return cand

        # 2. Si todos los candidatos existentes tienen un teléfono distinto registrado,
        # es una persona homónima distinta -> crear nuevo registro sin fusionar
        candidatos_sin_telefono = [c for c in candidatos if not c.telefono]
        candidatos_con_otro_telefono = [
            c for c in candidatos if c.telefono and c.telefono != cleaned_phone
        ]

        if candidatos_con_otro_telefono and not candidatos_sin_telefono:
            nuevo_homonimo = Cliente(
                nombre=cleaned_name,
                telefono=cleaned_phone,
                activo=True,
            )
            session.add(nuevo_homonimo)
            session.flush()
            return nuevo_homonimo

        # 3. Si existe un único cliente previo con ese nombre que aún no tenía teléfono registrado
        # (por ejemplo cliente real histórico o de retiro en local), se asocia y completa su teléfono
        if len(candidatos_sin_telefono) == 1 and not candidatos_con_otro_telefono:
            unico = candidatos_sin_telefono[0]
            es_hist, _, _ = classify_trace_origin(unico.notas)
            if not es_hist:
                unico.telefono = cleaned_phone
            session.flush()
            return unico

        # Si hay ambigüedad entre varios registros, crear uno nuevo con su teléfono propio
        nuevo_desambiguado = Cliente(
            nombre=cleaned_name,
            telefono=cleaned_phone,
            activo=True,
        )
        session.add(nuevo_desambiguado)
        session.flush()
        return nuevo_desambiguado

    # Sin teléfono en el pedido (ej. modalidad retiro)
    if len(candidatos) == 1:
        return candidatos[0]

    candidatos_sin_telefono = [c for c in candidatos if not c.telefono]
    if len(candidatos_sin_telefono) == 1:
        return candidatos_sin_telefono[0]

    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=(
            f"Existen múltiples clientes registrados con el nombre '{cleaned_name}'. "
            "Indique telefono_contacto o cliente_id para asociar el cliente correcto sin mezclar homónimos."
        ),
    )
