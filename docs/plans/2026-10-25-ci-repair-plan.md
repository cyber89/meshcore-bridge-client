# Corrección de CI del 2026-10-25

Origen: [ejecución 40147754527](https://github.com/cyber89/meshcore-bridge-client/actions/runs/40147754527),
commit `4e20035f3a270854ffeb83e20fdc6908696b9d41`.
El usuario autorizó expresamente pytest, cobertura y navegador aislado durante
esta tarea. Esa autorización no se extiende a tareas futuras.

## Plan y causas verificadas

1. Inspeccionar los cuatro jobs y reproducir los fallos con dependencias fijadas.
   Ruff, mypy, instalación de dependencias e instalación de Chromium habían
   pasado en la ejecución original; los pasos posteriores al primer fallo no
   estaban verificados.
2. Corregir la construcción de frontend. `theme.js` tenía CRLF localmente,
   mientras Git entregaba LF; el manifiesto conservaba el hash y tamaño de los
   bytes locales. Regenerar el manifiesto y rechazar fuentes CRLF antes del build.
3. Corregir once citas documentales a fuentes oficiales ausentes en un checkout
   normal. Sustituirlas por enlaces oficiales con SHA fijo, sin desactivar el
   validador ni descargar/modificar referencias.
4. Reparar fixtures obsoletas: claves públicas completas, SQLite temporal para
   comandos MQTT idempotentes y sincronización de recepción con `rx_router.drain()`.
5. Corregir identidades del adaptador virtual: sincronización y protocolo deben
   devolver las mismas claves completas de 32 bytes. Conservar selectores por
   prefijo, nombre y alias; exigir HTTP 200 en los envíos de las pruebas E2E.
6. Corregir el salto al último mensaje. Las alturas estimadas de
   `content-visibility` cambiaban después de situar el scroll al final; comprobar
   el resultado tras el renderizado, conservando foco y posición del documento.
7. Evitar que una acción Playwright bloqueada agote el watchdog global y pierda
   los resultados restantes. Limitar acciones a diez segundos y conservar los
   diagnósticos HTTP en los errores de consola.
8. Comprobar los pasos posteriores de CI. Las dos detecciones Bandit B104 en
   `get_status` correspondían a cadenas para advertir de exposición, sin apertura
   de sockets; documentar excepciones de esas dos líneas exclusivamente.
9. Revisar diff, publicar únicamente los archivos propios en `origin/main` y
   comprobar el resultado de la nueva ejecución en Linux con ambas versiones Python.
10. Revisar las áreas que la ejecución original no alcanzó: actualizar el selector
    de icono del modal al DOM vigente e instalar las herramientas frontend fijadas
    también en los jobs Python, para ejecutar las regresiones de build sin skips
    por ausencia de esbuild.
11. Conciliar la política de administración manual con el usuario. El 2026-10-25
    eligió mantener los cooldowns actuales también para las acciones manuales.
    Actualizar las regresiones y registrar la [decisión](../audits/2026-10-25-ci-repair.md)
    conservando el documento histórico de pausa 0.
12. Continuación del 2026-10-26: completar las ocho regresiones que permanecieron
    en `4721cf5`, incluidos sincronización de snapshots, admisión por rol,
    cooldown SENSOR, temas, tamaño táctil y respaldo seguro de mapas. Verificar
    el commit integrado mediante la matriz completa de Actions.

## Verificación y límites

La reproducción local utiliza una venv de QA independiente, CPython 3.12.10 en
Windows, los requirements fijados y Chromium de Playwright 1.64.0. No modifica
la venv operativa. Las pruebas usan almacenamiento temporal, radio virtual y
puertos loopback asignados por el SO; no transmiten RF ni conectan a un broker
operativo. WSL dispone de Python 3.14.4 sin herramientas de QA; no se presenta
como reproducción de la matriz Python 3.12/3.13.5 de Actions.

Los fallos del sandbox al crear `asyncio` mediante `socketpair` son una limitación
del entorno Windows; las comprobaciones asíncronas se ejecutan con acceso
loopback autorizado. Los skips por plataforma y las diferencias Git Bash/MSYS
se deben reportar aparte de los resultados de Ubuntu.

La aceptación requiere build/check, sintaxis JavaScript, documentación, Ruff,
mypy estricto, Bandit con el umbral vigente, contratos de importación/REST,
análisis de concurrencia y la suite mantenida con sus resultados reales. No
reducir expectativas, introducir `continue-on-error` ni desactivar jobs.
