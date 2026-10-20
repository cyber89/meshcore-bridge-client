# Selector web de conexión Companion

Fecha: 2026-10-17. Base: `0968eef`. Siguiente entrega de
[MeshCore1.18](../plans/MESHCORE_1_18_UPGRADE_PLAN.md), capa3.

## Implementación

La SPA ofrece herencia del entorno, USB/Serial y cliente TCP hacia la radio en
Ajustes → Servicios & Red. Distingue la conexión activa del destino para el
próximo arranque. Guardar no reconecta ni prueba conectividad; aplicar requiere
reiniciar manualmente el proceso del bridge. La configuración de servidor TCP
permanece en su formulario propio. No se ofrece actualización de firmware.

`ServicesConfig.companion_port` es una preferencia opcional, vacía por defecto.
Los documentos anteriores mantienen el comportamiento de `SERIAL_PORT`; borrar
la preferencia restaura esa herencia. La persistencia usa el documento SQLite
existente de servicios, fuera del event loop y bajo la propiedad de escritura
de `ServicesManager`, sin migración de esquema ni escritura de `.env`.

`normalize_companion_port` valida sin abrir sockets ni resolver nombres:
puerto explícito1..65535, host DNS/IPv4, ausencia de credenciales y componentes
URI ajenos al endpoint. IPv6 queda pendiente por el parser actual del adaptador.
Serial admite detección automática, COM y rutas absolutas. La validación del
controlador precede a los efectos de recarga incluso en peticiones mixtas.

## Contrato REST

Se amplía GET/POST `/api/services/config`; no hay rutas nuevas ni eventos WS.
Se conservan los controles de sesión, CSRF para cookie, API key y Origin.

| Campo | Contrato |
| --- | --- |
| POST `companion_port` | String opcional; omitir conserva, `""` hereda entorno. |
| GET/POST `data.companion_port` | Preferencia guardada, con proyección segura. |
| `data.companion_connection.configured_port` | Preferencia guardada para el próximo arranque. |
| `data.companion_connection.effective_port` | Preferencia o valor heredado del entorno. |
| `data.companion_connection.active_port` | Puerto del adaptador actualmente creado; no acredita enlace conectado. |
| `data.companion_connection.restart_required` | Diferencia del destino efectivo con el solicitado en el arranque actual. |

Éxito200 conserva `status:"ok"`, `data` y `reloaded`; guardar sólo Companion
produce `reloaded:[]`. Entrada inválida devuelve422 `invalid_companion_port`,
sin reflejar el valor recibido. Errores de persistencia/recarga conservan500
`reload_failed`; la autenticación mantiene sus respuestas existentes. El DTO
abierto y catálogo OpenAPI documentan el campo sin reemplazar validación runtime.

El formulario envía sólo `companion_port`, preserva borradores al refrescar otros
servicios, exige puerto explícito y conserva entradas tras fallos de guardado.
Los valores y errores se renderizan con `textContent`, con textos ES/EN.

## Impacto en malla

1. **Airtime:** guardar la preferencia agrega cero paquetes RF y no abre un
   enlace de prueba. Un futuro arranque usa el ciclo de vida existente.
2. **Spam/bucles:** sin nuevos publicadores MQTT, reintentos, consultas ni timers.
   Un guardado sólo Companion no recarga MQTT ni el servidor TCP.
3. **Guardado/reinicio:** no se alteran airtime, timestamps de administración,
   cooldowns ni schedulers. La preferencia es durable; no programa su aplicación
   automática. No se eligen nuevos intervalos ni umbrales.

## Verificación y pendientes

Las regresiones `tests/test_companion_connection.py` y
`tests/test_companion_connection_browser.py` se escribieron antes de la
implementación y **no se ejecutaron**: esta petición no autoriza suites según
AGENTS.md. No se atribuye ciclo TDD rojo/verde ni aceptación funcional o visual.
La selección todavía requiere QA aislado de API, persistencia y navegador en
1920×1080/390×844, incluidos auth/CSRF y conservación de borradores.

Comprobaciones estáticas ejecutadas y con salida satisfactoria:

- Ruff sobre las seis fuentes Python de la entrega y los dos tests nuevos.
- `mypy --strict src`:87 archivos sin incidencias.
- Build y `build_frontend.cjs --check`:31 assets coherentes con sus fuentes.
- `validate_project_docs.py`:103 documentos, cero incidencias.
- `audit_frontend_i18n.cjs`:1575 claves por idioma, sin findings léxicos; las
  expresiones dinámicas se revisaron directamente, sin certificar renderizado.
- `git diff --check`:sin errores de espacios.

No se inicia ni reinicia una estación operativa,
no se usa radio física y no se modifican las referencias oficiales.

La siguiente etapa del plan son los controles avanzados por hardware/rol de
capa4. Su selección requiere concretar controles RF; sensores activos de capa5
requieren decisiones del usuario sobre expiración, deltas y presupuesto.

Reversión: revertir el commit propio y reiniciar manualmente cuando corresponda;
versiones anteriores ignoran el campo adicional. El documento SQLite y los
datos existentes se conservan. Para volver a la selección de entorno en la
versión actual, guardar la opción de herencia antes de reiniciar el proceso.
