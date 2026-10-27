# Sabores del Llano

Base del frontend académico construida con React y Vite. El alcance actual se limita al enrutamiento y al shell administrativo compartido; las vistas funcionales, formularios, tablas con datos y operaciones siguen pendientes.

## Ejecutar

```sh
npm install
npm run dev
```

Para generar el bundle de producción, ejecuta 
pm run build`. Para servir ese bundle localmente, usa 
pm run preview`.

## Rutas preparadas

- `/app/dashboard` — Panel de Control
- `/app/orders` — Pedidos
- `/app/production` — Producción y análisis
- `/app/sales` — Ventas
- `/app/demand` — Predicción de demanda
- `/login` — acceso (placeholder)
- `/public` — portada (placeholder)

Las páginas administrativas comparten menú lateral, encabezado superior, tipografía y tokens de color. En pantallas menores a 800 px, el menú se convierte en un cajón móvil.

## Organización

`src/app` configura la aplicación y las rutas; `src/components/layout` contiene el shell administrativo; `src/components/ui` contiene encabezados y piezas visuales reutilizables; `src/features` reserva espacio por módulo; y `src/styles/index.css` reúne los tokens y estilos globales.

## Referencias Stitch

La fuente original está en el ZIP entregado por el usuario. Incluye la portada pública, inicio de sesión, cinco páginas administrativas y siete variantes de modales. Diez `screen.png` son archivos incompletos de 28 bytes con cabecera `GIF89a`; cuatro sí son PNG válidos. Los HTML y ambos `DESIGN.md` contienen el resto de las referencias visuales.

## Inicio de sesión de demostración

`/login` valida que los dos campos tengan contenido. Cualquier usuario y contraseña no vacíos habilitan el acceso local al panel; no se verifica identidad. El marcador `sabores-del-llano-demo-access` solo se guarda en `sessionStorage` para bloquear o permitir las rutas `/app/*` durante esta pestaña y se limpia al cerrar sesión. Las contraseñas no se almacenan. Esto no sustituye la autenticación del backend.

## Pedidos

Los pedidos usan `localStorage` mediante el servicio del módulo. Los registros de demostración solo se cargan cuando el almacenamiento no contiene todavía la clave de pedidos; eliminar todos los pedidos deja una lista vacía incluso después de recargar. El panel de control lee el mismo servicio para el contador y los últimos pedidos.

## Panel de control

El panel calcula las ventas y cantidades desde sus datos demo, y lee el conteo y los pedidos recientes del servicio compartido del módulo Pedidos.


