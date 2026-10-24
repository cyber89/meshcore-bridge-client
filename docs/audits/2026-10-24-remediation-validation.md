# Corrección de los hallazgos de documentación, scripts y contratos — 2026-10-24

Inicio: 2026-10-23; integración continuada el 2026-10-24. Base: `c3b114c`, rama `main`. El usuario solicita solucionar los problemas
encontrados en las dos revisiones. Se conservan ambos informes como evidencia
histórica; este registro distingue implementación y comprobaciones ejecutadas.

## Alcance y propiedad

- Instaladores: permisos, reinstalación, puertos COM, credenciales y Mosquitto.
- Servicios: locks/tareas de canales, presets, capacidades y recuperación local.
- Herramientas: códigos de salida, inspección visual, diagramas y contratos de imports.
- Integración principal: identidad DM, validación de canales, ledger MQTT en workers,
  deduplicación administrativa, perfiles mínimos, OpenAPI y documentación conjunta.

Se añadirán regresiones aisladas sin ejecutarlas: `AGENTS.md` mantiene las suites
suspendidas hasta petición explícita. Se permiten lectura, AST, sintaxis,
Ruff/mypy, revisión de contratos y verificaciones documentales sin arrancar la
aplicación. No se utilizará hardware, configuración o datos de una estación real.

## Checklist obligatorio de impacto en malla

1. **Airtime:** no se añaden paquetes, consultas periódicas ni reintentos. Se
   corrigen operaciones solicitadas por el usuario/consumidor y se conserva
   `TxRateLimiter`, las prioridades y todos los presupuestos existentes. Resolver
   un alias DM antes de persistir permite el envío ya solicitado a su identidad
   canónica; no agrega otro envío. La sincronización de canales conserva las
   consultas Companion locales existentes.
2. **Spam y feedback:** no se crean publicaciones automáticas ni puentes nuevos.
   Las órdenes identificadas se reservarán antes de despachar, también en la ruta
   administrativa por repetidor; una reserva rechazada o inaccesible no disparará
   RF. El modo legado sin ID mantiene su compatibilidad y las guardas LOCAL y
   REPEATER siguen vigentes. No se eligen límites o intervalos nuevos.
3. **Configuración y timers:** no se crean/rearman timers ni se alteran timestamps
   de airtime o cooldown. La persistencia sigue siendo SQLite. La actualización
   conserva datos/configuración y la recuperación de cuenta no borra la base.

## Verificación de referencia

Antes de integrar cambios, el mypy local 2.3.1 con `--strict src` terminó con
`Success: no issues found in 97 source files`. Ruff local disponible: 0.16.3.
Estos datos identifican las herramientas usadas, no las versiones declaradas por
el perfil dev. Los resultados finales y las limitaciones se registrarán al cerrar
la corrección; no se atribuirá aprobación dinámica a las regresiones no ejecutadas.

## Cambios implementados

| Hallazgo | Corrección y evidencia |
| --- | --- |
| D01: lock reentrante de canales | La ruta HTTP sync deja el lock a `ChannelService.sync_from_radio`; no lo adquiere por segunda vez. |
| D02: permisos de `.env` | La creación inicial usa apertura exclusiva y modo 0600; update restringe el archivo conservado y rechaza symlinks. |
| D03: reinstalación destructiva | El modo normal rechaza un destino existente antes de APT, broker o borrado. Se requiere `--update` con staging y rollback. |
| D04: COM convertido en carácter | El resultado ordenado se captura siempre como array en `install.ps1`. |
| D05: tarea de escritura fallida | El servicio observa/libera writers terminados, conserva los pendientes ante cancelación y permite lecturas/reintentos posteriores. |
| D06: preset que contamina configuración | Se valida/persiste una copia y sólo después se publica la nueva lista; guardado y borrado conservan propiedad de la transacción ante cancelación. |
| D07: DM sin identidad canónica | `MessageService` resuelve una clave completa y rechaza ambigüedad antes de encolar; el core revalida antes de crear el feed y enviar. Se conservan las guardas LOCAL/REPEATER, también para contactos SDK. |
| D08: SQLite en el loop | Reserva, marca de despacho y resultado usan workers propios protegidos con shield; cierre drena sólo esos workers. |
| D09: core siempre starting | Arranque/apagado actualizan core; consultas y métricas refrescan estado observado de radio/red sin timer nuevo. Un core detenido no conserva salud disponible. |
| D10: canal fraccionario | El ingreso de chat admite sólo enteros y representaciones enteras; no trunca floats antes de RF. |
| D11: exportación vacía con éxito | JSON ausente/error devuelve exit 1 sin sobrescribir el archivo de salida existente. |
| D12: PASS visual vacío | Requiere sesión cookie autorizada, estación visible y componentes; comprueba errores por separado en desktop y móvil. `--storage-state` selecciona una sesión existente; no se agrega Bearer a URLs arbitrarias. |
| D13: diagramas sin fuentes | Cualquier fuente requerida ausente o entrega incompleta devuelve fallo y no anuncia compilación total. |
| D14: salud frontend sin exit de fallo | Excepciones, HTTP/red, consola y componentes ausentes influyen en el código de salida. |
| D15: descendientes fuera del gate | El checker expande los orígenes de paquete a todos sus módulos descendientes y conserva el recorrido transitivo. |

Los pendientes adicionales de la primera pasada también se concilian:

- **Mosquitto:** contraseña generada exclusivamente con `secrets` del intérprete
  seleccionado; sin fallback fijo. Password file temporal, publicación con
  propietario/grupo `root:mosquitto` y modo 0640; errores de aprovisionamiento y
  arranque se propagan. La configuración inicial inserta claves que falten en la
  plantilla. Update conserva configuración/broker existentes y no rota credenciales.
- **Recuperación local:** no admite contraseña por argumento; exige terminal y
  aborta si `getpass` no puede ocultar entrada. Selecciona `.env` de la instalación
  indicada, rechaza symlinks y comprueba autoridad POSIX, identidad del archivo y
  generación de la cuenta antes del cambio transaccional. No crea cuentas nuevas.
  En Windows siguen siendo responsabilidad del operador las ACL NTFS del directorio.
- **Ledger administrativo:** ambas rutas comparten reserva, incluidas órdenes
  todavía sin resultado. Con ID, un fallo de almacenamiento impide despacho; el
  modo legado sólo se admite sin ID. Se mantiene el límite de 10 000 filas y la
  ausencia de replay. Reserva, RF y resultado no forman una transacción conjunta:
  no se promete ejecución exactamente una vez.
  La integración conserva también el destino broadcast de mensajes MQTT legados
  sin destino explícito; un destino JSON explícitamente nulo sigue rechazándose.
- **Perfiles:** base/core sólo requiere MeshCore, pyserial y dotenv. Extras MQTT,
  web, all y dev añaden sus dependencias; `requirements.txt` y los instaladores
  completos conservan toda la pila y comprueban `--profile all`. La fachada MQTT
  desactivada no carga Paho/TLS. Se añaden manifiestos core y MQTT.
- **OpenAPI:** ambas rutas de capacidades están registradas y documentadas con
  autenticación y respuesta pasiva. Se actualizan las guías y el inventario.

## Regresiones escritas, no ejecutadas

Se añaden cinco módulos en `tests/test_deep_*`: instaladores, servicios,
mensajería/ledger, perfiles de runtime y herramientas. Usan temporales, mocks,
radio falsa o validación de salidas; no habilitan una radio o un broker real.
Se adapta el fixture mantenido de instaladores al rechazo de reinstalación y al
perfil completo. Los casos incluyen duplicados pendientes, ruta por repetidor,
thread del ledger, feed DM canónico, recuperación concurrente, cambios fallidos
de presets, falta de fuentes y falsos resultados PASS.

No se ejecutaron pytest, navegador, fuzzing, instaladores, recuperación, servicios
ni hardware. La revisión de las regresiones y las comprobaciones estáticas no
acreditan su aprobación. Tampoco se ejecutó una instalación en Linux/SBC/Windows
ni se probaron callbacks Paho o interoperabilidad física.

## Resultado de las comprobaciones ejecutadas

| Herramienta/alcance | Resultado observado |
| --- | --- |
| Ruff local 0.16.3: `ruff check src tests scripts` | `All checks passed!`. |
| Mypy local 2.3.1: `--strict src scripts/check_runtime_dependencies.py scripts/reset_web_password.py` | `Success: no issues found in 99 source files`. |
| AST Python con mínimo 3.12 | 30 archivos Python modificados/nuevos y 1 bloque Python embebido del instalador; 0 incidencias de sintaxis. |
| Parser PowerShell de `install.ps1` | 0 incidencias de sintaxis; no se ejecutó el instalador. |
| Git Bash `bash -n install.sh` | Exit 0; sólo parseo. |
| `python scripts/check_layer_contracts.py` | 2 contratos; 0 infracciones estáticas detectadas. |
| `python scripts/validate_project_docs.py` | 132 documentos/skills; 0 incidencias estructurales o de enlaces locales. |
| `python scripts/inventory_verification.py` | 185 archivos inventariados sin ejecutarlos; el JSON local conserva hashes y distingue evidencia histórica. |
| `python scripts/inventory_project_knowledge.py --write` | Snapshot regenerado con HEAD de base y hashes del árbol revisado; cotejado con disco antes de publicar. |
| `git diff --check` e índice de publicación | Sin incidencias; sólo archivos de la tarea. |
| Pytest/cobertura, navegador y fuzzing | No ejecutados: requieren petición explícita según `AGENTS.md`. No se reportan porcentajes ni aprobaciones. |

Los archivos ajenos `auditoria.reporte.md` y `exploracion.md` no se leen, editan ni
publican. No se actualizan dependencias, intérpretes globales o referencias. Un
commit/push no equivale a desplegar una estación ni acredita funcionamiento RF.
