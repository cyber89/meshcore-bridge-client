# Entrega del frontend y compresión HTTP

Implementación: 2026-10-10. La SPA conserva HTML, Bootstrap, CSS y módulos ES
nativos. Los contratos REST/WebSocket, roles de nodos y operaciones RF no cambian.

## Construcción reproducible

Node.js >=18 y esbuild 0.28.1 son herramientas de construcción, no dependencias
del servicio Python. Desde la raíz:

```sh
npm --prefix tools/frontend ci
npm --prefix tools/frontend run build
npm --prefix tools/frontend run check
```

`scripts/build_frontend.cjs` transforma cada JS/CSS propio por separado, conserva
imports relativos y globals de scripts clásicos, y escribe variantes `.min.js` /
`.min.css`. Los originales siguen siendo las fuentes editables. El build crea
gzip nivel 9 para HTML, CSS y JS; verifica su descompresión contra los bytes que
se sirven y publica `src/web/static/asset-manifest.json` al final. `--check`
reconstruye en memoria y compara los artefactos sin escribir archivos.

Los artefactos están incluidos en Git y en los package-data de `src.web`; un SBC
no necesita Node ni compilar al instalar o arrancar. Las reglas LF de
`.gitattributes` conservan los hashes entre Windows y Linux. Después de modificar
fuentes hay que ejecutar build antes de publicar; check detecta recibos obsoletos.
No se usan regex para minimizar código JS/CSS.

El tema Zephyr servido es una copia derivada sin su import de Google Fonts:
`bootstrap-zephyr.local.min.css`. El vendor original y sus licencias/hashes
permanecen conservados. El HTML y CSS propios usan fuentes del sistema.

## Selección y caché

`AssetsAdapter` mantiene las URLs originales. Selecciona la variante minimizada
cuando coinciden los SHA256 de fuente y destino registrados en el manifest;
selecciona gzip solo si también coincide su digest y el navegador lo acepta.
No comprime archivos durante las peticiones. La lectura y los hashes se ejecutan
fuera de asyncio y se cachean por ruta, tamaño y mtime; cambiar el manifest lo
invalida. Los límites de ruta y symlinks siguen confinados al directorio estático.

Sin manifest válido o tras editar una fuente, sirve el original sin gzip. Si solo
el gzip es inválido, sirve el minificado sin compresión. Cada representación
tiene su ETag y `Vary: Accept-Encoding`; se conserva el cache-control existente
(HTML no-store; otros estáticos 300 segundos). La negociación respeta `gzip;q=0`
incluso cuando existe un wildcard. HEAD conserva la supresión de cuerpo del
perímetro de seguridad.

## Presupuesto de CPU de compresión dinámica

`BridgeCompressionMiddleware` está dentro del perímetro de seguridad. Solo
comprime respuestas JSON GET 200, no transmitidas como stream, de 1 KiB a 1 MiB
en estas rutas de métricas:

- `/api/analytics` y `/api/metrics/analytics`
- `/api/lqi`
- `/api/rf/heatmap` y `/api/rf/noise`
- `/api/airtime/stats`

No comprime configuración, claves, exportaciones, canales, mensajes, logs, docs,
WebSockets, teselas, errores, HEAD, respuestas parciales, datos ya codificados,
respuestas con cookies/ETag ni las que solicitan `Cache-Control: no-transform`.

El único trabajo admitido usa zlib nivel 1 fuera del event loop. Mide el tiempo
de CPU del hilo (`thread_time`) y el tiempo real (`monotonic`), trabaja en bloques
de 32 KiB y descansa en el worker hasta que el consumo acumulado de compresión
ocupa como máximo el 50% de un núcleo en el trabajo. Las peticiones concurrentes
se sirven sin comprimir; no forman una cola de compresión. Cancelar una petición
no libera el puesto mientras el worker sigue activo.

Este presupuesto regula el consumo medio del worker; un bloque puede producir
un pico breve antes del descanso. No equivale a una cuota instantánea del sistema
operativo ni limita el proceso bridge. El usuario acotó expresamente el 50% al
trabajo de compresión. La implementación no acredita consumo de CPU real ni
rendimiento en un SBC sin mediciones de carga autorizadas.

## Alcance de comprobación

La construcción y su comprobación verifican sintaxis parseable, artefactos,
hashes y gzip. La revisión estática revisa referencias y contratos; no acredita
layout de navegador, accesibilidad completa, interoperabilidad HTTP o rendimiento.
En esta entrega, 22 assets del catálogo local suman 1.940.079 bytes de fuentes,
1.674.827 bytes servidos minimizados y 324.289 bytes gzip (83,3% menos que las
fuentes). El catálogo incluye ambos temas y el CSS base; estas cifras no son una
medición de descarga inicial ni incluyen Leaflet, fuentes de iconos o teselas.
Se comprobaron sintaxis de 31 JS (fuentes y variantes), Ruff y mypy estricto sobre
los tres módulos Python modificados (`--follow-imports=silent`). La máquina de
QA disponible tiene Python 3.12; no se ejecutó el servicio ni se acredita aquí
runtime CPython 3.14.8. La dependencia de build se reutilizó de la caché local
esbuild 0.28.1; el lockfile conserva versión e integridades de paquetes npm.
pytest/Playwright y mediciones de carga requieren petición explícita según
[AGENTS.md](../AGENTS.md). No se inicia una estación ni se transmite por radio
para construir estos archivos.
