# Plan de integración de almacenamiento — 2026-10-10

Solicitud: SQLite es la fuente principal de mensajes, conversaciones, estados de
entrega y estado actualmente persistido en JSON. IndexedDB es caché de mensajes;
LocalStorage conserva preferencias visuales, idioma y paneles. CPython mínimo
3.12 estable; recomendado 3.13.5.

## Alcance y secuencia

1. Inventariar las rutas actuales y definir un adaptador SQLite común usando la
   biblioteca estándar. Versionar el esquema; transacciones, WAL en disco local,
   sincronización durable y operaciones de disco fuera de asyncio.
2. Importar una sola vez canales, registro de nodos, airtime, configuración de
   servicios/presets y cooldowns de repetidores. Respetar sus rutas configuradas,
   validar las fuentes y conservar los JSON originales como respaldo histórico.
   No volver a importar un JSON antiguo sobre datos ya migrados.
3. Inyectar el adaptador en los componentes de producción. Mantener las cachés
   RAM, locks y generaciones existentes; SQLite sustituye las escrituras JSON.
   Conservar .env para configuración de arranque, MBTiles, manifiestos de assets
   y formatos JSON de API/importación/exportación: no son archivos de estado.
4. Persistir RX, TX y cambios de ACK desde el bridge, independientemente de la
   interfaz web. Consultar historial por conversación con paginación y claves
   estables; conservar estados de entrega sin degradar un ACK confirmado.
5. Integrar API y navegador: SQLite manda, IndexedDB sirve como caché por estación
   y fallback sin conexión, LocalStorage sólo preferencias. Ofrecer importación
   explícita del historial local anterior, deduplicada y sin transmisión por RF.
   Mantener autenticación de las lecturas y escrituras de historial.
6. Actualizar arquitectura, dominio, despliegue, README en inglés y ADR 0017,
   sustituyendo la decisión de persistencia de ADR 0005 donde corresponda.
7. Rehacer JS/CSS minificado y gzip; revisar diff, sintaxis, tipos y documentación.
   Las suites pytest/Playwright no están autorizadas en esta solicitud y no se
   ejecutarán. Preparar regresiones aisladas y registrar límites reales.

## Propiedad de archivos y coordinación

- Adaptador SQLite: esquema, migración, consultas y regresiones del repositorio.
- Persistencia de dominio: nodos, servicios, canales, airtime y cooldowns.
- Frontend: caché, historial, importación, preferencias y credenciales de sesión.
- Principal: lifecycle, eventos RX/TX/ACK, API, integración, documentación y entrega.

## Conservación de datos y operación

La base reside bajo DATA_DIR, con una ruta explícita configurable. Los errores
de migración/escritura se propagan; no se anunciará persistencia exitosa ni se
reemplazará estado válido por valores vacíos. Respaldos SQLite usan su API de
backup, no una copia parcial del archivo mientras está abierto en WAL. No se
introducirá borrado automático de historial ni un plazo de retención arbitrario.
Las credenciales y PSK necesitan permisos restrictivos en la base y sus respaldos.

## Impacto en la malla LoRa

- Airtime adicional: cero. Sólo se almacenan eventos existentes; consultar o
  importar historial no genera paquetes ni consultas activas de radio.
- Spam/feedback: no se publica de nuevo el historial en MQTT ni se reencolan TX.
  Se conservan deduplicación e invariantes LOCAL/REPEATER.
- Timers: no se añaden timers RF ni se cambian intervalos. La migración conserva
  timestamps de cooldown y airtime; guardar configuración no reinicia esas fechas.

## Criterios de entrega

Producción usa SQLite para las cinco fuentes de estado; mensajes se almacenan
sin clientes web conectados; múltiples navegadores consultan el mismo historial
autorizado y mantienen cachés aisladas por estación. Migración repetida no duplica
ni sobrescribe. La entrega distingue comprobaciones estáticas, regresiones
preparadas y despliegue real, que no se ejecuta sobre una estación operativa.

## Resultado de implementación

Implementación integrada el 2026-10-10: `StationDatabase` y validadores compartidos,
inyección en las cinco fuentes de estado, captura RX/TX sin web, correlaciones ACK
durables y consumo/entrega atómicos, `HistoryController` y catálogo OpenAPI,
IndexedDB por estación, paginación, importación explícita y credenciales de pestaña.
README, dominio, arquitectura, despliegue, reglas y ADR 0017 actualizados.
Los JSON se importarán durante el próximo arranque; no se abrió una instalación
operativa ni se ejecutó esa migración durante el desarrollo.

Evidencia estática: Ruff correcto en producción y regresiones nuevas; mypy estricto
correcto en 89 archivos (producción/configuración y cuatro módulos nuevos de
regresión); AST válido en 91 archivos; siete fuentes JS verificadas con
`node --check`; build/check de 22 recursos minificados y gzip correcto;
`git diff --check` correcto. Estas cifras describen cobertura estática, no pruebas
de comportamiento. No se ejecutaron pytest, Playwright ni fuzzing. Las regresiones
preparadas deben ejecutarse cuando se solicite QA explícito, incluyendo la UI
IndexedDB/DOM real y los fixtures existentes afectados por el cambio de autoridad.
