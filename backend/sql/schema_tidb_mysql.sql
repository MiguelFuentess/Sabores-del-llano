-- ============================================================================
-- Sabores del Llano — Esquema relacional para MySQL 8.0+ y TiDB Cloud Serverless
-- ============================================================================
-- Script DDL idempotente (CREATE TABLE IF NOT EXISTS) ordenado topológicamente
-- según las dependencias de claves foráneas (12 tablas del dominio).
--
-- Ejecución recomendada:
--   1) Seleccionar previamente la base de datos destino (ej. Base de datos sabores_del_llano)
--   2) Ejecutar este archivo en TiDB Cloud SQL Editor, MySQL Workbench o cliente CLI.
--   3) Alternativa desde Python: python -m app.db.init_schema
-- ============================================================================

SET NAMES utf8mb4;
SET time_zone = '-05:00';

-- 1. Clientes
CREATE TABLE IF NOT EXISTS `clientes` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `nombre` VARCHAR(120) NOT NULL,
  `telefono` VARCHAR(30) DEFAULT NULL,
  `correo` VARCHAR(150) DEFAULT NULL,
  `notas` VARCHAR(500) DEFAULT NULL,
  `activo` TINYINT(1) NOT NULL DEFAULT '1',
  `creado_en` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `actualizado_en` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_clientes_nombre` (`nombre`),
  KEY `idx_clientes_telefono` (`telefono`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci /*T![auto_id_cache] AUTO_ID_CACHE=1 */;

-- 2. Usuarios administrativos
CREATE TABLE IF NOT EXISTS `usuarios` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `nombre_usuario` VARCHAR(80) NOT NULL,
  `nombre_completo` VARCHAR(120) NOT NULL,
  `password_hash` VARCHAR(255) NOT NULL,
  `activo` TINYINT(1) NOT NULL DEFAULT '1',
  `ultimo_acceso` DATETIME DEFAULT NULL,
  `creado_en` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `actualizado_en` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `nombre_usuario` (`nombre_usuario`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci /*T![auto_id_cache] AUTO_ID_CACHE=1 */;

-- 3. Productos del catálogo
CREATE TABLE IF NOT EXISTS `productos` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `nombre` VARCHAR(100) NOT NULL,
  `descripcion` VARCHAR(500) DEFAULT NULL,
  `unidad_base` VARCHAR(30) NOT NULL,
  `activo` TINYINT(1) NOT NULL DEFAULT '1',
  `creado_en` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `actualizado_en` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `nombre` (`nombre`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci /*T![auto_id_cache] AUTO_ID_CACHE=1 */;

-- 4. Presentaciones comerciales por producto
CREATE TABLE IF NOT EXISTS `presentaciones` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `producto_id` BIGINT UNSIGNED NOT NULL,
  `nombre` VARCHAR(100) NOT NULL,
  `unidad_venta` VARCHAR(30) NOT NULL,
  `factor_conversion` DECIMAL(12,4) NOT NULL,
  `precio_actual` DECIMAL(12,2) NOT NULL DEFAULT '0.00',
  `activo` TINYINT(1) NOT NULL DEFAULT '1',
  `creado_en` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `actualizado_en` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_presentacion_producto_nombre` (`producto_id`, `nombre`),
  CONSTRAINT `fk_presentaciones_producto` FOREIGN KEY (`producto_id`) REFERENCES `productos` (`id`) ON DELETE RESTRICT ON UPDATE CASCADE,
  CONSTRAINT `presentaciones_chk_1` CHECK ((`factor_conversion` > 0)),
  CONSTRAINT `presentaciones_chk_2` CHECK ((`precio_actual` >= 0))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci /*T![auto_id_cache] AUTO_ID_CACHE=1 */;

-- 5. Pedidos
CREATE TABLE IF NOT EXISTS `pedidos` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `cliente_id` BIGINT UNSIGNED DEFAULT NULL,
  `fecha_pedido` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `fecha_entrega_prevista` DATETIME DEFAULT NULL,
  `estado` ENUM('pendiente','confirmado','en_preparacion','entregado','cancelado') NOT NULL DEFAULT 'pendiente',
  `nombre_contacto` VARCHAR(120) DEFAULT NULL,
  `telefono_contacto` VARCHAR(30) DEFAULT NULL,
  `direccion_entrega` VARCHAR(255) DEFAULT NULL,
  `observaciones` VARCHAR(1000) DEFAULT NULL,
  `creado_en` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `actualizado_en` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_pedidos_cliente` (`cliente_id`),
  KEY `idx_pedidos_fecha_estado` (`fecha_pedido`, `estado`),
  KEY `idx_pedidos_entrega_estado` (`fecha_entrega_prevista`, `estado`),
  CONSTRAINT `pedidos_ibfk_1` FOREIGN KEY (`cliente_id`) REFERENCES `clientes` (`id`) ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci /*T![auto_id_cache] AUTO_ID_CACHE=1 */;

-- 6. Detalle de pedidos
CREATE TABLE IF NOT EXISTS `detalle_pedidos` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `pedido_id` BIGINT UNSIGNED NOT NULL,
  `presentacion_id` BIGINT UNSIGNED NOT NULL,
  `cantidad` DECIMAL(12,3) NOT NULL,
  `precio_unitario` DECIMAL(12,2) NOT NULL,
  `factor_conversion_snapshot` DECIMAL(12,4) NOT NULL,
  `observaciones` VARCHAR(500) DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `idx_detalle_pedidos_pedido` (`pedido_id`),
  KEY `idx_detalle_pedidos_presentacion` (`presentacion_id`),
  CONSTRAINT `detalle_pedidos_ibfk_1` FOREIGN KEY (`pedido_id`) REFERENCES `pedidos` (`id`) ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT `detalle_pedidos_ibfk_2` FOREIGN KEY (`presentacion_id`) REFERENCES `presentaciones` (`id`) ON DELETE RESTRICT ON UPDATE CASCADE,
  CONSTRAINT `detalle_pedidos_chk_1` CHECK ((`cantidad` > 0)),
  CONSTRAINT `detalle_pedidos_chk_2` CHECK ((`precio_unitario` >= 0)),
  CONSTRAINT `detalle_pedidos_chk_3` CHECK ((`factor_conversion_snapshot` > 0))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci /*T![auto_id_cache] AUTO_ID_CACHE=1 */;

-- 7. Ventas
CREATE TABLE IF NOT EXISTS `ventas` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `pedido_id` BIGINT UNSIGNED DEFAULT NULL,
  `fecha_venta` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `estado` ENUM('concretada','anulada') NOT NULL DEFAULT 'concretada',
  `observaciones` VARCHAR(1000) DEFAULT NULL,
  `creado_en` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `pedido_id` (`pedido_id`),
  KEY `idx_ventas_fecha_estado` (`fecha_venta`, `estado`),
  CONSTRAINT `ventas_ibfk_1` FOREIGN KEY (`pedido_id`) REFERENCES `pedidos` (`id`) ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci /*T![auto_id_cache] AUTO_ID_CACHE=1 */;

-- 8. Detalle de ventas
CREATE TABLE IF NOT EXISTS `detalle_ventas` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `venta_id` BIGINT UNSIGNED NOT NULL,
  `presentacion_id` BIGINT UNSIGNED NOT NULL,
  `cantidad` DECIMAL(12,3) NOT NULL,
  `precio_unitario` DECIMAL(12,2) NOT NULL,
  `factor_conversion_snapshot` DECIMAL(12,4) NOT NULL,
  PRIMARY KEY (`id`),
  KEY `idx_detalle_ventas_venta` (`venta_id`),
  KEY `idx_detalle_ventas_presentacion` (`presentacion_id`),
  CONSTRAINT `detalle_ventas_ibfk_1` FOREIGN KEY (`venta_id`) REFERENCES `ventas` (`id`) ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT `detalle_ventas_ibfk_2` FOREIGN KEY (`presentacion_id`) REFERENCES `presentaciones` (`id`) ON DELETE RESTRICT ON UPDATE CASCADE,
  CONSTRAINT `detalle_ventas_chk_1` CHECK ((`cantidad` > 0)),
  CONSTRAINT `detalle_ventas_chk_2` CHECK ((`precio_unitario` >= 0)),
  CONSTRAINT `detalle_ventas_chk_3` CHECK ((`factor_conversion_snapshot` > 0))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci /*T![auto_id_cache] AUTO_ID_CACHE=1 */;

-- 9. Producciones
CREATE TABLE IF NOT EXISTS `producciones` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `producto_id` BIGINT UNSIGNED NOT NULL,
  `fecha_produccion` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `cantidad_producida_base` DECIMAL(12,3) NOT NULL,
  `observaciones` VARCHAR(1000) DEFAULT NULL,
  `creado_en` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `producto_id` (`producto_id`),
  KEY `idx_producciones_fecha_producto` (`fecha_produccion`, `producto_id`),
  CONSTRAINT `producciones_ibfk_1` FOREIGN KEY (`producto_id`) REFERENCES `productos` (`id`) ON DELETE RESTRICT ON UPDATE CASCADE,
  CONSTRAINT `producciones_chk_1` CHECK ((`cantidad_producida_base` > 0))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci /*T![auto_id_cache] AUTO_ID_CACHE=1 */;

-- 10. Movimientos de inventario (Kardex en unidad base)
CREATE TABLE IF NOT EXISTS `movimientos_inventario` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `producto_id` BIGINT UNSIGNED NOT NULL,
  `produccion_id` BIGINT UNSIGNED DEFAULT NULL,
  `detalle_venta_id` BIGINT UNSIGNED DEFAULT NULL,
  `tipo` ENUM('saldo_inicial','produccion','venta','ajuste_entrada','ajuste_salida') NOT NULL,
  `fecha_movimiento` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `cantidad_base` DECIMAL(12,3) NOT NULL,
  `observaciones` VARCHAR(500) DEFAULT NULL,
  `creado_en` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_movimientos_producto_fecha` (`producto_id`, `fecha_movimiento`),
  KEY `idx_movimientos_produccion` (`produccion_id`),
  KEY `idx_movimientos_detalle_venta` (`detalle_venta_id`),
  CONSTRAINT `fk_movimientos_detalle_venta` FOREIGN KEY (`detalle_venta_id`) REFERENCES `detalle_ventas` (`id`) ON DELETE RESTRICT ON UPDATE CASCADE,
  CONSTRAINT `fk_movimientos_produccion` FOREIGN KEY (`produccion_id`) REFERENCES `producciones` (`id`) ON DELETE RESTRICT ON UPDATE CASCADE,
  CONSTRAINT `fk_movimientos_producto` FOREIGN KEY (`producto_id`) REFERENCES `productos` (`id`) ON DELETE RESTRICT ON UPDATE CASCADE,
  CONSTRAINT `chk_movimientos_cantidad` CHECK ((`cantidad_base` > 0))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci /*T![auto_id_cache] AUTO_ID_CACHE=1 */;

-- 11. Cierres diarios de inventario
CREATE TABLE IF NOT EXISTS `cierres_diarios` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `producto_id` BIGINT UNSIGNED NOT NULL,
  `fecha` DATE NOT NULL,
  `existencia_calculada_base` DECIMAL(12,3) NOT NULL,
  `sobrante_real_base` DECIMAL(12,3) NOT NULL,
  `diferencia_base` DECIMAL(12,3) GENERATED ALWAYS AS ((`sobrante_real_base` - `existencia_calculada_base`)) STORED,
  `observaciones` VARCHAR(500) DEFAULT NULL,
  `usuario_id` BIGINT UNSIGNED DEFAULT NULL,
  `creado_en` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_cierre_producto_fecha` (`producto_id`, `fecha`),
  KEY `fk_cierres_usuario` (`usuario_id`),
  KEY `idx_cierres_fecha` (`fecha`),
  CONSTRAINT `fk_cierres_producto` FOREIGN KEY (`producto_id`) REFERENCES `productos` (`id`) ON DELETE RESTRICT ON UPDATE CASCADE,
  CONSTRAINT `fk_cierres_usuario` FOREIGN KEY (`usuario_id`) REFERENCES `usuarios` (`id`) ON DELETE SET NULL ON UPDATE CASCADE,
  CONSTRAINT `chk_cierres_existencia` CHECK ((`existencia_calculada_base` >= 0)),
  CONSTRAINT `chk_cierres_sobrante` CHECK ((`sobrante_real_base` >= 0))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci /*T![auto_id_cache] AUTO_ID_CACHE=1 */;

-- 12. Gastos e inversiones operativas
CREATE TABLE IF NOT EXISTS `gastos` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `fecha` DATE NOT NULL,
  `concepto` VARCHAR(180) NOT NULL,
  `categoria` ENUM('ingredientes','empaques','servicios','transporte','equipos','otros') NOT NULL DEFAULT 'otros',
  `tipo` ENUM('gasto','inversion') NOT NULL DEFAULT 'gasto',
  `valor` DECIMAL(12,2) NOT NULL,
  `observaciones` VARCHAR(1000) DEFAULT NULL,
  `usuario_id` BIGINT UNSIGNED DEFAULT NULL,
  `creado_en` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `actualizado_en` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `fk_gastos_usuario` (`usuario_id`),
  KEY `idx_gastos_fecha_categoria` (`fecha`, `categoria`),
  KEY `idx_gastos_tipo_fecha` (`tipo`, `fecha`),
  CONSTRAINT `fk_gastos_usuario` FOREIGN KEY (`usuario_id`) REFERENCES `usuarios` (`id`) ON DELETE SET NULL ON UPDATE CASCADE,
  CONSTRAINT `chk_gastos_valor` CHECK ((`valor` > 0))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci /*T![auto_id_cache] AUTO_ID_CACHE=1 */;
