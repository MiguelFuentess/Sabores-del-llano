# RESUMEN DE TRANSFERENCIA
# SABORES DEL LLANO

## 1. Contexto

Sabores del Llano es un proyecto universitario de práctica profesional para desarrollar una aplicación web de gestión de un negocio familiar dedicado a comercializar Hayacas y Lechona en Colombia.

El objetivo es centralizar la gestión de pedidos, ventas, producción, inventario, gastos y análisis de demanda.

## 2. Tecnologías

| Componente | Tecnología |
|---|---|
| Frontend | React |
| Herramienta frontend | Vite |
| Backend | Python |
| API | FastAPI |
| ORM | SQLAlchemy |
| Base de datos | MySQL |

Base de datos:

`sabores_del_llano`

## 3. Estructura general

```text
Sabores del llano - Practica profesional/
│
├── src/
│   ├── features/
│   │   ├── auth/
│   │   ├── orders/
│   │   ├── demand/
│   │   ├── public/
│   │   ├── sales/
│   │   └── otros módulos
│   │
│   ├── components/
│   │   └── ui/
│   │
│   └── demás archivos frontend
│
├── backend/
├── package.json
└── demás archivos de configuración
```

## 4. Módulos

| Módulo | Responsabilidad |
|---|---|
| auth | Inicio de sesión |
| dashboard | Resumen general |
| orders | Pedidos individuales |
| producción | Producción y sobrantes |
| sales | Ventas |
| demand | Predicción de demanda |
| public | Sitio público y calculadora de lechona |

La estructura exacta debe verificarse en el repositorio.

## 5. Reglas de negocio fundamentales

### Productos

- Hayaca: unidad base Unidad.
- Lechona: unidad base Plato.
- Precio de referencia Hayaca: $10.000.
- Precio de referencia Lechona: $12.000.

### Pedidos

- Exclusivamente individuales.
- No inventar pedidos masivos.
- No inventar eventos.
- El campo de cliente debe permitir escritura libre.
- Domicilio debe mostrar dirección y teléfono.

### Fechas

Ventas, producción y sobrantes deben corresponder únicamente a sábados, domingos o festivos nacionales colombianos.

### Producción

Regla confirmada:

`Producción = Ventas + Sobrantes`

### Datos sintéticos

Deben identificarse como sintéticos y no confundirse con registros reales.

## 6. Módulo de demanda

Ruta:

`src/features/demand`

El selector de periodo histórico debe utilizar:

- `fechaDesde`
- `fechaHasta`

Debe validar que la fecha inicial no sea posterior a la final.

El rango mínimo obligatorio todavía no se ha definido.

El modelo debe considerar festivos colombianos, vacaciones escolares, temporadas y eventos relevantes, utilizando información verificable.

## 7. Calculadora pública

Ruta:

`src/features/public`

Calculadora exclusiva de lechona.

Precios proporcionados:

- Plato individual: $12.000.
- Cojín para 25 personas: $320.000.
- Cojín para 50 personas: $520.000.

Fórmula provisional acordada:

- 5 a 25 personas: interpolación entre $60.000 y $320.000.
- 25 a 50 personas: interpolación entre $320.000 y $520.000.
- Más de 50: incremento provisional de $8.000 por persona.

Valores de referencia:

| Personas | Precio |
|---:|---:|
| 5 | $60.000 |
| 10 | $125.000 |
| 25 | $320.000 |
| 50 | $520.000 |
| 100 | $920.000 |
| 150 | $1.320.000 |

Verificar si la fórmula ya está implementada.

## 8. Datos históricos

Se trabajó con un Excel que contiene:

- Productos y presentaciones.
- Historial de ventas.
- Pedidos.
- Producción.
- Sobrantes.

Archivo depurado conocido:

`Datos_sabores_del_llano_depurado.xlsx`

Datos identificados:

- 98 registros de ventas.
- 211 pedidos.
- 98 registros de producción reconstruida.
- 98 registros de sobrantes.
- Periodo original: junio a octubre de 2026.
- Total de ventas registrado: $136.290.000.

Se acordó ampliar el periodo desde noviembre de 2024 hasta octubre de 2026.

La ampliación debe utilizar datos sintéticos claramente identificados.

Reducción histórica aproximada: entre 5 % y 8 % anual respecto al nivel de referencia de 2026.

No asumir que la ampliación ya está realizada.

## 9. Base de datos

El diseño inicial contempla:

1. clientes
2. usuarios
3. productos
4. presentaciones
5. pedidos
6. detalle_pedidos
7. ventas
8. detalle_ventas
9. producciones
10. movimientos_inventario
11. cierres_diarios
12. gastos

Verificar el esquema MySQL real antes de realizar modificaciones.

## 10. Decisiones de desarrollo

- Trabajar módulo por módulo.
- No modificar archivos ajenos a la tarea.
- No refactorizar sin necesidad.
- Conservar el diseño existente.
- No modificar backend por ajustes visuales.
- No modificar MySQL sin autorización.
- Identificar siempre los datos sintéticos.
- No inventar reglas de negocio.
- Validar cada modificación antes de continuar.

## 11. Próximos pasos recomendados

1. Auditar el estado actual del frontend.
2. Finalizar los ajustes visuales pendientes.
3. Revisar el Excel histórico ampliado.
4. Verificar el esquema MySQL.
5. Completar el backend.
6. Integrar progresivamente los módulos.
7. Implementar la predicción de demanda.
8. Ejecutar pruebas integrales.

## 12. Primera instrucción para el nuevo agente

Antes de modificar cualquier archivo:

1. Lee `DOCUMENTACION_TECNICA.md`.
2. Inspecciona la estructura real del repositorio.
3. Identifica las diferencias entre documentación y código.
4. Resume el estado real del proyecto.
5. No modifiques nada hasta recibir la primera tarea del usuario.

**El desarrollo debe continuar de manera gradual, ordenada y con autorización del usuario para cada cambio.**