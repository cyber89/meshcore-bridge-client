---
name: installer-release-maintenance
description: Revisar o mantener instaladores raíz, servicio systemd y publicación Git de MeshCore Bridge; comprobar rutas, entorno Python y códigos de salida antes de ejecutar cambios autorizados.
---

# Instaladores y publicación

Usar para cambios o auditorías de install.sh, install.ps1, meshcore-bridge.service
y entrega Git. Leer [AGENTS.md](../../../AGENTS.md),
[DEPLOYMENT_GUIDE.md](../../../docs/DEPLOYMENT_GUIDE.md) y los pendientes de
[PROJECT_KNOWLEDGE.md](../../../docs/PROJECT_KNOWLEDGE.md).

- Revisar antes de ejecutar: instalar/actualizar/desinstalar puede cambiar
  servicios, permisos, datos y transmitir al arrancar el bridge. Una revisión
  documental permite lectura y análisis, no ejecutar un instalador en producción.
  No recrear deploy/ o scripts/sync_deploy.py.
- Acreditar intérprete y entorno usados por pip, launcher y servicio. Mantener
  Python >=3.10 y separar dependencias de producción/QA. Usar herramientas locales;
  no actualizar paquetes/globales por conveniencia de la auditoría.
- Resolver rutas origen/destino antes de borrar, mover o copiar recursivamente.
  El update debe conservar .env y datos y funcionar cuando origen coincide con
  instalación: no borrar src antes de acreditar otra copia independiente.
  En Windows usar un único shell y cmdlets con LiteralPath para esos movimientos.
- Propagar fallos y códigos de salida. No anunciar QA aprobado por un exit 0
  que ha silenciado errores con `|| true` o sin verificar LASTEXITCODE.
  `scripts/run_quality_checks.py` ejecuta pytest/mypy/ruff/docs; las suites siguen
  requiriendo petición explícita. Registrar qué comprobaciones realmente corrieron.
- Antes de publicar comprobar rama, origin, HEAD, estado e índice. Revisar diff
  y añadir únicamente archivos/hunks propios; en checkout sucio aislar los cambios
  sin stash/reset de trabajo ajeno. AGENTS.md autoriza commit y push origin main
  al completar modificaciones; no forzar ni mezclar cambios de otras tareas.
  Si hay divergencia remota, resolver sólo el trabajo propio o informar el bloqueo.
- No asumir despliegue exitoso por un push. Distinguir revisión, commit, push e
  instalación ejecutada. Registrar resultados y límites en el ledger mediante el
  principal; radio/timers/MQTT nuevos requieren el checklist RF y límites acordados.
