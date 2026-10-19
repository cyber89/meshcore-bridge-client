# Primer acceso y comprobación de sesión — 2026-10-18

La ayuda «¿Es tu primer acceso?» se mostraba siempre, incluso después de cambiar
las credenciales. Además, la consulta de sesión esperaba la carga de los módulos
de la aplicación mientras el contenedor de login ya era visible.

## Corrección

- El servidor publica `requires_initial_setup` en `AuthSession`, también para
  visitantes anónimos. Lo obtiene del estado persistido del propietario; no
  depende de cookies de presentación ni del almacenamiento del navegador.
- La ayuda permanece oculta hasta que el servidor confirma que falta el cambio
  inicial. Tras cambiar la contraseña, cerrar sesión o reabrir SQLite, permanece
  oculta. El cambio inicial obligatorio conserva su diálogo y bloqueo de acceso.
- Un script de arranque inicia la consulta antes de completar las dependencias
  de la aplicación. El módulo reutiliza la promesa o hace una sola consulta si
  ese script llega tarde. Los errores se capturan desde el inicio.
- Durante la comprobación sólo aparece la marca con un estado para lectores de
  pantalla. Una cookie válida permite entrar sin mostrar el formulario. Si la
  consulta falla, aparece el login con el error correspondiente, sin afirmar que
  sea el primer acceso.

No cambia la duración de sesión, la validación CSRF ni la autorización de API o
WebSocket. No se leen contraseñas guardadas por el navegador ni se guardan
secretos nuevos. Con una sesión caducada sigue siendo necesario iniciar sesión;
el navegador puede completar las credenciales guardadas mediante su gestor.

## Verificación

Regresiones iniciales reprodujeron la falta del estado persistido, la ayuda
incondicional, el formulario visible durante la consulta y el retraso causado
por una dependencia de la aplicación retenida. Se corrigió también la limpieza
del interceptor usado por la prueba inicial antes de comprobar el resultado.

Las comprobaciones usan SQLite temporal y una estación virtual en loopback:

- 52 casos aprobados: `test_auth_startup_state.py`,
  `test_auth_startup_browser.py` (seis casos de navegador en esa ejecución),
  `test_web_authentication.py` y `test_auth_setup.py`.
- 24 casos aprobados: flujo de perfil/validación Unicode/logout de
  `test_login_browser_audit.py`, `test_chat_reading_browser.py` y
  `test_js_dialog_regressions.py`.
- Un caso adicional aprobado de distribución del login en 32 combinaciones:
  temas claro/oscuro, español/inglés, cuatro viewports de 320 a 1920 px y ayuda
  abierta/cerrada. Comprueba desbordamiento horizontal y acceso al botón.
- Ruff y mypy estricto aprobados para los dos archivos Python de producción y
  los dos archivos de regresión modificados/añadidos.
- Compilación y recibos de 32 assets verificados; auditoría i18n sin hallazgos,
  con 1651 claves por idioma.

Artefactos locales ignorados: `tests/artifacts/auth-startup/`, incluidos los tres
XML finales y `login-reflow.json`. No se ejecutó la suite completa ni cobertura.
El caso histórico de matriz visual del login contiene colores anteriores al
tema vigente; la nueva regresión comprueba geometría sin reutilizar esos colores.
No se midió latencia de una instalación real ni se usaron radios o brokers de
producción. La comprobación adelantada reduce la espera por módulos; la entrada
sigue dependiendo de la respuesta de red y la validación del servidor.
