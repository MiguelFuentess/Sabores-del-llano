from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
     Boolean,
    CheckConstraint,
    Computed,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Numeric,
    String,
    TIMESTAMP,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.mysql import BIGINT, TINYINT
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import MYSQL_TABLE_ARGS, Base

UNSIGNED_BIGINT = BIGINT(unsigned=True)
TINYINT_BOOL = TINYINT(1)
PK_BIGINT = BIGINT(unsigned=True)


class Cliente(Base):
    __tablename__ = "clientes"
    __table_args__ = (
        Index("idx_clientes_nombre", "nombre"),
        Index("idx_clientes_telefono", "telefono"),
        MYSQL_TABLE_ARGS,
    )

    id: Mapped[int] = mapped_column(PK_BIGINT, primary_key=True, autoincrement=True)
    nombre: Mapped[str] = mapped_column(String(120), nullable=False)
    telefono: Mapped[str | None] = mapped_column(String(30), nullable=True)
    correo: Mapped[str | None] = mapped_column(String(150), nullable=True)
    notas: Mapped[str | None] = mapped_column(String(500), nullable=True)
    activo: Mapped[bool] = mapped_column(
        TINYINT_BOOL, nullable=False, default=True, server_default=text("'1'")
    )
    creado_en: Mapped[datetime] = mapped_column(
        TIMESTAMP, nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    actualizado_en: Mapped[datetime] = mapped_column(
        TIMESTAMP,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
    )

    pedidos: Mapped[list[Pedido]] = relationship(back_populates="cliente")


class Usuario(Base):
    __tablename__ = "usuarios"
    __table_args__ = (
        UniqueConstraint("nombre_usuario", name="nombre_usuario"),
        MYSQL_TABLE_ARGS,
    )

    id: Mapped[int] = mapped_column(PK_BIGINT, primary_key=True, autoincrement=True)
    nombre_usuario: Mapped[str] = mapped_column(String(80), nullable=False)
    nombre_completo: Mapped[str] = mapped_column(String(120), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    activo: Mapped[bool] = mapped_column(
        TINYINT_BOOL, nullable=False, default=True, server_default=text("'1'")
    )
    ultimo_acceso: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    creado_en: Mapped[datetime] = mapped_column(
        TIMESTAMP, nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    actualizado_en: Mapped[datetime] = mapped_column(
        TIMESTAMP,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
    )

    cierres_diarios: Mapped[list[CierreDiario]] = relationship(back_populates="usuario")
    gastos: Mapped[list[Gasto]] = relationship(back_populates="usuario")


class Producto(Base):
    __tablename__ = "productos"
    __table_args__ = (
        UniqueConstraint("nombre", name="nombre"),
        MYSQL_TABLE_ARGS,
    )

    id: Mapped[int] = mapped_column(PK_BIGINT, primary_key=True, autoincrement=True)
    nombre: Mapped[str] = mapped_column(String(100), nullable=False)
    descripcion: Mapped[str | None] = mapped_column(String(500), nullable=True)
    unidad_base: Mapped[str] = mapped_column(String(30), nullable=False)
    activo: Mapped[bool] = mapped_column(
        TINYINT_BOOL, nullable=False, default=True, server_default=text("'1'")
    )
    creado_en: Mapped[datetime] = mapped_column(
        TIMESTAMP, nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    actualizado_en: Mapped[datetime] = mapped_column(
        TIMESTAMP,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
    )

    presentaciones: Mapped[list[Presentacion]] = relationship(
        back_populates="producto", order_by="Presentacion.id"
    )
    producciones: Mapped[list[Produccion]] = relationship(back_populates="producto")
    movimientos_inventario: Mapped[list[MovimientoInventario]] = relationship(
        back_populates="producto"
    )
    cierres_diarios: Mapped[list[CierreDiario]] = relationship(
        back_populates="producto"
    )


class Presentacion(Base):
    __tablename__ = "presentaciones"
    __table_args__ = (
        UniqueConstraint(
            "producto_id", "nombre", name="uq_presentacion_producto_nombre"
        ),
        CheckConstraint("factor_conversion > 0", name="presentaciones_chk_1"),
        CheckConstraint("precio_actual >= 0", name="presentaciones_chk_2"),
        MYSQL_TABLE_ARGS,
    )

    id: Mapped[int] = mapped_column(PK_BIGINT, primary_key=True, autoincrement=True)
    producto_id: Mapped[int] = mapped_column(
        UNSIGNED_BIGINT,
        ForeignKey(
            "productos.id",
            name="fk_presentaciones_producto",
            ondelete="RESTRICT",
            onupdate="CASCADE",
        ),
        nullable=False,
    )
    nombre: Mapped[str] = mapped_column(String(100), nullable=False)
    unidad_venta: Mapped[str] = mapped_column(String(30), nullable=False)
    factor_conversion: Mapped[Decimal] = mapped_column(
        Numeric(12, 4), nullable=False
    )
    precio_actual: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
        default=Decimal("0.00"),
        server_default=text("'0.00'"),
    )
    activo: Mapped[bool] = mapped_column(
        TINYINT_BOOL, nullable=False, default=True, server_default=text("'1'")
    )
    creado_en: Mapped[datetime] = mapped_column(
        TIMESTAMP, nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    actualizado_en: Mapped[datetime] = mapped_column(
        TIMESTAMP,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
    )

    producto: Mapped[Producto] = relationship(back_populates="presentaciones")
    detalles_pedido: Mapped[list[DetallePedido]] = relationship(
        back_populates="presentacion"
    )
    detalles_venta: Mapped[list[DetalleVenta]] = relationship(
        back_populates="presentacion"
    )


class Pedido(Base):
    __tablename__ = "pedidos"
    __table_args__ = (
        Index("idx_pedidos_cliente", "cliente_id"),
        Index("idx_pedidos_fecha_estado", "fecha_pedido", "estado"),
        Index("idx_pedidos_entrega_estado", "fecha_entrega_prevista", "estado"),
        MYSQL_TABLE_ARGS,
    )

    id: Mapped[int] = mapped_column(PK_BIGINT, primary_key=True, autoincrement=True)
    cliente_id: Mapped[int | None] = mapped_column(
        UNSIGNED_BIGINT,
        ForeignKey(
            "clientes.id",
            name="pedidos_ibfk_1",
            ondelete="RESTRICT",
            onupdate="CASCADE",
        ),
        nullable=True,
    )
    fecha_pedido: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    fecha_entrega_prevista: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True
    )
    estado: Mapped[str] = mapped_column(
        Enum(
            "pendiente",
            "confirmado",
            "en_preparacion",
            "entregado",
            "cancelado",
            name="pedido_estado_enum",
        ),
        nullable=False,
        default="pendiente",
        server_default=text("'pendiente'"),
    )
    nombre_contacto: Mapped[str | None] = mapped_column(String(120), nullable=True)
    telefono_contacto: Mapped[str | None] = mapped_column(String(30), nullable=True)
    direccion_entrega: Mapped[str | None] = mapped_column(String(255), nullable=True)
    observaciones: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    creado_en: Mapped[datetime] = mapped_column(
        TIMESTAMP, nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    actualizado_en: Mapped[datetime] = mapped_column(
        TIMESTAMP,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
    )

    cliente: Mapped[Cliente | None] = relationship(back_populates="pedidos")
    detalles: Mapped[list[DetallePedido]] = relationship(
        back_populates="pedido", cascade="all, delete-orphan"
    )
    venta: Mapped[Venta | None] = relationship(back_populates="pedido")


class DetallePedido(Base):
    __tablename__ = "detalle_pedidos"
    __table_args__ = (
        Index("idx_detalle_pedidos_pedido", "pedido_id"),
        Index("idx_detalle_pedidos_presentacion", "presentacion_id"),
        CheckConstraint("cantidad > 0", name="detalle_pedidos_chk_1"),
        CheckConstraint("precio_unitario >= 0", name="detalle_pedidos_chk_2"),
        CheckConstraint("factor_conversion_snapshot > 0", name="detalle_pedidos_chk_3"),
        MYSQL_TABLE_ARGS,
    )

    id: Mapped[int] = mapped_column(PK_BIGINT, primary_key=True, autoincrement=True)
    pedido_id: Mapped[int] = mapped_column(
        UNSIGNED_BIGINT,
        ForeignKey(
            "pedidos.id",
            name="detalle_pedidos_ibfk_1",
            ondelete="CASCADE",
            onupdate="CASCADE",
        ),
        nullable=False,
    )
    presentacion_id: Mapped[int] = mapped_column(
        UNSIGNED_BIGINT,
        ForeignKey(
            "presentaciones.id",
            name="detalle_pedidos_ibfk_2",
            ondelete="RESTRICT",
            onupdate="CASCADE",
        ),
        nullable=False,
    )
    cantidad: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    precio_unitario: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    factor_conversion_snapshot: Mapped[Decimal] = mapped_column(
        Numeric(12, 4), nullable=False
    )
    observaciones: Mapped[str | None] = mapped_column(String(500), nullable=True)

    pedido: Mapped[Pedido] = relationship(back_populates="detalles")
    presentacion: Mapped[Presentacion] = relationship(
        back_populates="detalles_pedido"
    )


class Venta(Base):
    __tablename__ = "ventas"
    __table_args__ = (
        UniqueConstraint("pedido_id", name="pedido_id"),
        Index("idx_ventas_fecha_estado", "fecha_venta", "estado"),
        MYSQL_TABLE_ARGS,
    )

    id: Mapped[int] = mapped_column(PK_BIGINT, primary_key=True, autoincrement=True)
    pedido_id: Mapped[int | None] = mapped_column(
        UNSIGNED_BIGINT,
        ForeignKey(
            "pedidos.id",
            name="ventas_ibfk_1",
            ondelete="RESTRICT",
            onupdate="CASCADE",
        ),
        nullable=True,
    )
    fecha_venta: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    estado: Mapped[str] = mapped_column(
        Enum("concretada", "anulada", name="venta_estado_enum"),
        nullable=False,
        default="concretada",
        server_default=text("'concretada'"),
    )
    observaciones: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    creado_en: Mapped[datetime] = mapped_column(
        TIMESTAMP, nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )

    pedido: Mapped[Pedido | None] = relationship(back_populates="venta")
    detalles: Mapped[list[DetalleVenta]] = relationship(
        back_populates="venta", cascade="all, delete-orphan"
    )


class DetalleVenta(Base):
    __tablename__ = "detalle_ventas"
    __table_args__ = (
        Index("idx_detalle_ventas_venta", "venta_id"),
        Index("idx_detalle_ventas_presentacion", "presentacion_id"),
        CheckConstraint("cantidad > 0", name="detalle_ventas_chk_1"),
        CheckConstraint("precio_unitario >= 0", name="detalle_ventas_chk_2"),
        CheckConstraint("factor_conversion_snapshot > 0", name="detalle_ventas_chk_3"),
        MYSQL_TABLE_ARGS,
    )

    id: Mapped[int] = mapped_column(PK_BIGINT, primary_key=True, autoincrement=True)
    venta_id: Mapped[int] = mapped_column(
        UNSIGNED_BIGINT,
        ForeignKey(
            "ventas.id",
            name="detalle_ventas_ibfk_1",
            ondelete="CASCADE",
            onupdate="CASCADE",
        ),
        nullable=False,
    )
    presentacion_id: Mapped[int] = mapped_column(
        UNSIGNED_BIGINT,
        ForeignKey(
            "presentaciones.id",
            name="detalle_ventas_ibfk_2",
            ondelete="RESTRICT",
            onupdate="CASCADE",
        ),
        nullable=False,
    )
    cantidad: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    precio_unitario: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    factor_conversion_snapshot: Mapped[Decimal] = mapped_column(
        Numeric(12, 4), nullable=False
    )

    venta: Mapped[Venta] = relationship(back_populates="detalles")
    presentacion: Mapped[Presentacion] = relationship(
        back_populates="detalles_venta"
    )
    movimientos_inventario: Mapped[list[MovimientoInventario]] = relationship(
        back_populates="detalle_venta"
    )


class Produccion(Base):
    __tablename__ = "producciones"
    __table_args__ = (
        Index("producto_id", "producto_id"),
        Index("idx_producciones_fecha_producto", "fecha_produccion", "producto_id"),
        CheckConstraint("cantidad_producida_base > 0", name="producciones_chk_1"),
        MYSQL_TABLE_ARGS,
    )

    id: Mapped[int] = mapped_column(PK_BIGINT, primary_key=True, autoincrement=True)
    producto_id: Mapped[int] = mapped_column(
        UNSIGNED_BIGINT,
        ForeignKey(
            "productos.id",
            name="producciones_ibfk_1",
            ondelete="RESTRICT",
            onupdate="CASCADE",
        ),
        nullable=False,
    )
    fecha_produccion: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    cantidad_producida_base: Mapped[Decimal] = mapped_column(
        Numeric(12, 3), nullable=False
    )
    observaciones: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    creado_en: Mapped[datetime] = mapped_column(
        TIMESTAMP, nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )

    producto: Mapped[Producto] = relationship(back_populates="producciones")
    movimientos_inventario: Mapped[list[MovimientoInventario]] = relationship(
        back_populates="produccion"
    )


class MovimientoInventario(Base):
    __tablename__ = "movimientos_inventario"
    __table_args__ = (
        Index("idx_movimientos_producto_fecha", "producto_id", "fecha_movimiento"),
        Index("idx_movimientos_produccion", "produccion_id"),
        Index("idx_movimientos_detalle_venta", "detalle_venta_id"),
        CheckConstraint("cantidad_base > 0", name="chk_movimientos_cantidad"),
        MYSQL_TABLE_ARGS,
    )

    id: Mapped[int] = mapped_column(PK_BIGINT, primary_key=True, autoincrement=True)
    producto_id: Mapped[int] = mapped_column(
        UNSIGNED_BIGINT,
        ForeignKey(
            "productos.id",
            name="fk_movimientos_producto",
            ondelete="RESTRICT",
            onupdate="CASCADE",
        ),
        nullable=False,
    )
    produccion_id: Mapped[int | None] = mapped_column(
        UNSIGNED_BIGINT,
        ForeignKey(
            "producciones.id",
            name="fk_movimientos_produccion",
            ondelete="RESTRICT",
            onupdate="CASCADE",
        ),
        nullable=True,
    )
    detalle_venta_id: Mapped[int | None] = mapped_column(
        UNSIGNED_BIGINT,
        ForeignKey(
            "detalle_ventas.id",
            name="fk_movimientos_detalle_venta",
            ondelete="RESTRICT",
            onupdate="CASCADE",
        ),
        nullable=True,
    )
    tipo: Mapped[str] = mapped_column(
        Enum(
            "saldo_inicial",
            "produccion",
            "venta",
            "ajuste_entrada",
            "ajuste_salida",
            name="movimiento_inventario_tipo_enum",
        ),
        nullable=False,
    )
    fecha_movimiento: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    cantidad_base: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    observaciones: Mapped[str | None] = mapped_column(String(500), nullable=True)
    creado_en: Mapped[datetime] = mapped_column(
        TIMESTAMP, nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )

    producto: Mapped[Producto] = relationship(
        back_populates="movimientos_inventario"
    )
    produccion: Mapped[Produccion | None] = relationship(
        back_populates="movimientos_inventario"
    )
    detalle_venta: Mapped[DetalleVenta | None] = relationship(
        back_populates="movimientos_inventario"
    )


class CierreDiario(Base):
    __tablename__ = "cierres_diarios"
    __table_args__ = (
        UniqueConstraint("producto_id", "fecha", name="uq_cierre_producto_fecha"),
        Index("fk_cierres_usuario", "usuario_id"),
        Index("idx_cierres_fecha", "fecha"),
        CheckConstraint("existencia_calculada_base >= 0", name="chk_cierres_existencia"),
        CheckConstraint("sobrante_real_base >= 0", name="chk_cierres_sobrante"),
        MYSQL_TABLE_ARGS,
    )

    id: Mapped[int] = mapped_column(PK_BIGINT, primary_key=True, autoincrement=True)
    producto_id: Mapped[int] = mapped_column(
        UNSIGNED_BIGINT,
        ForeignKey(
            "productos.id",
            name="fk_cierres_producto",
            ondelete="RESTRICT",
            onupdate="CASCADE",
        ),
        nullable=False,
    )
    fecha: Mapped[date] = mapped_column(Date, nullable=False)
    existencia_calculada_base: Mapped[Decimal] = mapped_column(
        Numeric(12, 3), nullable=False
    )
    sobrante_real_base: Mapped[Decimal] = mapped_column(
        Numeric(12, 3), nullable=False
    )
    diferencia_base: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 3),
        Computed("sobrante_real_base - existencia_calculada_base", persisted=True),
        nullable=True,
    )
    observaciones: Mapped[str | None] = mapped_column(String(500), nullable=True)
    usuario_id: Mapped[int | None] = mapped_column(
        UNSIGNED_BIGINT,
        ForeignKey(
            "usuarios.id",
            name="fk_cierres_usuario",
            ondelete="SET NULL",
            onupdate="CASCADE",
        ),
        nullable=True,
    )
    creado_en: Mapped[datetime] = mapped_column(
        TIMESTAMP, nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )

    producto: Mapped[Producto] = relationship(back_populates="cierres_diarios")
    usuario: Mapped[Usuario | None] = relationship(back_populates="cierres_diarios")


class Gasto(Base):
    __tablename__ = "gastos"
    __table_args__ = (
        Index("fk_gastos_usuario", "usuario_id"),
        Index("idx_gastos_fecha_categoria", "fecha", "categoria"),
        Index("idx_gastos_tipo_fecha", "tipo", "fecha"),
        CheckConstraint("valor > 0", name="chk_gastos_valor"),
        MYSQL_TABLE_ARGS,
    )

    id: Mapped[int] = mapped_column(PK_BIGINT, primary_key=True, autoincrement=True)
    fecha: Mapped[date] = mapped_column(Date, nullable=False)
    concepto: Mapped[str] = mapped_column(String(180), nullable=False)
    categoria: Mapped[str] = mapped_column(
        Enum(
            "ingredientes",
            "empaques",
            "servicios",
            "transporte",
            "equipos",
            "otros",
            name="gasto_categoria_enum",
        ),
        nullable=False,
        default="otros",
        server_default=text("'otros'"),
    )
    tipo: Mapped[str] = mapped_column(
        Enum("gasto", "inversion", name="gasto_tipo_enum"),
        nullable=False,
        default="gasto",
        server_default=text("'gasto'"),
    )
    valor: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    observaciones: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    usuario_id: Mapped[int | None] = mapped_column(
        UNSIGNED_BIGINT,
        ForeignKey(
            "usuarios.id",
            name="fk_gastos_usuario",
            ondelete="SET NULL",
            onupdate="CASCADE",
        ),
        nullable=True,
    )
    creado_en: Mapped[datetime] = mapped_column(
        TIMESTAMP, nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    actualizado_en: Mapped[datetime] = mapped_column(
        TIMESTAMP,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
    )

    usuario: Mapped[Usuario | None] = relationship(back_populates="gastos")


__all__ = [
    "Base",
    "CierreDiario",
    "Cliente",
    "DetallePedido",
    "DetalleVenta",
    "Gasto",
    "MovimientoInventario",
    "Pedido",
    "Presentacion",
    "Produccion",
    "Producto",
    "Usuario",
    "Venta",
]
