# Autenticación de la estación personal

Fecha: 2026-10-12. Plan revisado por los agentes de backend/seguridad, frontend e instalación, coordinados por el principal.

## Alcance y decisiones

Una cuenta de operador protege todos los datos y operaciones HTTP de `/api/`, las teselas locales, la documentación API y los WebSockets. La página y los recursos estáticos necesarios para iniciar sesión son públicos. MQTT y el protocolo TCP Companion conservan sus controles independientes; no utilizan la cookie web.

Las contraseñas usan `hashlib.scrypt` con sal aleatoria y parámetros N=32768, r=8, p=3. Esta configuración figura entre las opciones mínimas de [OWASP Password Storage](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html) y limita la memoria del hash a aproximadamente 32 MiB como coste algorítmico, sin presentar una medición de la estación. El hash y SQLite se ejecutan fuera del event loop. Se limita la concurrencia del trabajo criptográfico y se controla la frecuencia de intentos de acceso.

El navegador utiliza una cookie de sesión opaca, `HttpOnly`, `SameSite=Strict`, con `Secure` cuando se accede por HTTPS. El servidor guarda el digest del identificador de sesión, su vencimiento y el token CSRF en SQLite. “Recordarme” conserva la sesión durante 30 días; sin esa opción la cookie es de sesión y el servidor impone un máximo de 12 horas. No se almacena el secreto de sesión en LocalStorage, SessionStorage ni URLs. Las mutaciones con cookie requieren `X-CSRF-Token`; el login y los WebSockets validan el origen. Véase [OWASP Session Management](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html).

Las automatizaciones pueden obtener un token opaco y enviarlo por `Authorization: Bearer`. Su digest se persiste y el secreto se entrega una sola vez. La clave `BRIDGE_API_KEY` explícitamente configurada se mantiene para clientes existentes por cabecera, sin aceptar credenciales en query. El cambio de credenciales revoca sesiones y tokens generados; la clave externa de `.env` necesita rotación independiente.

Nombre de usuario: entre 1 y 64 letras ASCII, dígitos, puntos, guiones o guiones bajos. Contraseña nueva: entre 15 y 128 caracteres, sin reglas de composición; se permite pegar y usar gestores de contraseñas. El cambio de cuenta requiere la contraseña actual.

## Etapas y propiedad de archivos

1. **Inspección y acuerdo de contrato.** Identificar guardas existentes, puntos de arranque SPA, almacenamiento y secuencia de los instaladores. Fijar los endpoints antes de editar los consumidores.
2. **Backend y persistencia.** Agente backend: repositorio de autenticación, middleware, endpoints, WebSocket y OpenAPI. Preparar regresiones aisladas antes de implementación; no ejecutar suites durante esta solicitud.
3. **Instalación.** Agente instaladores: `install.sh`, `install.ps1`, `scripts/setup_auth.py` y guía de despliegue. Solicitar nombre, contraseña oculta y confirmación con un plazo total de 180 segundos. Si vence o no hay terminal interactivo, usar `admin:admin`. Conservar la cuenta existente al actualizar.
4. **Interfaz.** Agente frontend: archivos estáticos, login previo al arranque de módulos, recordar sesión, cuenta, logout, token de integración y manejo de expiración/CSRF. Regenerar activos minificados y gzip.
5. **Integración y revisión.** Principal: revisar diffs, contratos, documentación y comprobaciones estáticas. Publicar únicamente archivos propios de la tarea, manteniendo los cambios previos del usuario.

## Contrato HTTP

| Ruta | Método | Uso |
| --- | --- | --- |
| `/api/auth/session` | GET | Estado de sesión y CSRF; no expone datos de estación a visitantes. |
| `/api/auth/login` | POST | `{username,password,remember}`; establece cookie. |
| `/api/auth/logout` | POST | Revoca la sesión y elimina cookie; exige CSRF. |
| `/api/auth/credentials` | PUT | `{current_password,username,password}`; cambia cuenta, revoca accesos previos y renueva sesión. |
| `/api/auth/api-token` | POST | `{current_password}`; genera/rota token para integración. |

Estado de sesión: `{authenticated,username,csrf_token,must_change_credentials,api_key_configured}`. Un visitante recibe un estado anónimo sin secretos de una cuenta. Los endpoints de cuenta requieren sesión de navegador. Errores de autenticación: 401; CSRF/origen o cambio obligatorio: 403; limitación de intentos: 429.

`admin:admin` es una credencial de arranque explícita solicitada por el usuario. Se marca como cambio obligatorio: permite iniciar sesión y cambiar credenciales, pero no consultar datos, abrir WebSockets ni utilizar un token de integración. No se sustituye una cuenta válida con el valor de arranque al reiniciar o guardar configuración.

## Impacto en la malla

1. **Airtime:** cero paquetes adicionales. La autenticación sólo opera sobre HTTP, SQLite y el navegador.
2. **Spam y feedback:** no publica MQTT, no notifica automáticamente y no reintenta comandos RF. Volver a iniciar sesión nunca reproduce una mutación pendiente.
3. **Timers y configuración:** no incorpora un scheduler de radio ni altera airtime/cooldowns. Los vencimientos de sesión se comprueban por acceso y se persisten; el guardado de configuración no los rearma.

## Evidencia y límites

La petición autoriza implementar y revisar el plan, pero no ejecutar pytest, Playwright ni fuzzing. Se preparan regresiones y se realizan inspección de fuentes, sintaxis, Ruff, mypy y build estático cuando las herramientas estén disponibles. Esos controles no acreditan funcionamiento dinámico, layout en navegador ni seguridad completa. No se ejecutan instaladores, se inicia una estación operativa ni se transmite por hardware.

HTTPS protege contraseñas y cookies durante el transporte. En una instalación HTTP local `HttpOnly` y CSRF no cifran el tráfico; para acceso remoto se debe usar un proxy HTTPS. El fallback conocido tampoco demuestra posesión exclusiva de la cuenta: el primer acceso debe completar el cambio de contraseña.

La confianza de cabeceras del proxy es optativa: `BRIDGE_TRUSTED_PROXY_IPS` declara sus IP exactas; vacío la desactiva. El proxy debe conservar el `Host` público y sobrescribir `X-Forwarded-Proto`/`X-Forwarded-For`. Para un proxy en el mismo host se puede configurar `127.0.0.1,::1` y restringir el listener del bridge a ese proxy. Esto permite reconocer HTTPS y marcar las cookies Secure sin confiar en cabeceras de clientes arbitrarios.

## Registro de entrega

Las etapas de implementación y revisión de fuentes se completaron el 2026-10-12. El agente de instaladores realizó una revisión de seguridad independiente del backend; el principal revisó directamente los diffs y las fronteras API/SPA/instaladores. Se corrigieron la limitación de contraseña actual, las carreras de revocación, la conservación del slot criptográfico durante cancelación, el acceso WebSocket posterior a revocación, la confianza explícita del proxy HTTPS y la caché de respuestas autenticadas (`no-store`, preservando `Vary`).

| Comprobación | Evidencia y alcance |
| --- | --- |
| Runtime reutilizado | CPython 3.12.14 del `.venv` existente; no se instalaron dependencias de producción nuevas. |
| Ruff | 0.16.3 instalado; comprobación de las fuentes Python modificadas y regresiones nuevas, sin errores. |
| Mypy strict | 2.3.1 instalado; diez archivos de backend/configuración/helper, sin errores. |
| Sintaxis | Compilación Python, parser PowerShell, `bash -n install.sh` y sintaxis JS modificada, correctos. Los instaladores no se ejecutaron. |
| Frontend | esbuild 0.28.1 existente; build y `node scripts/build_frontend.cjs --check` verifican 30 activos, 1.952.568 bytes servidos y 397.895 bytes gzip. Son tamaños de build, no mediciones de runtime. |
| Estructura HTML | Inspección estática del agente frontend: 587 IDs únicos, referencias ARIA/for y selectores válidos, 34 claves nuevas ES/EN. No acredita layout renderizado. |
| Bandit | Análisis de los dos módulos nuevos de autenticación: cero hallazgos medios/altos; dos hallazgos bajos B105 por el literal `admin` solicitado para bootstrap. Se conservan y documentan sin ocultarlos. |
| Documentación | `scripts/validate_project_docs.py`: 91 documentos revisados y seis problemas preexistentes de estructura/metadatos en ADR 0017. ADR 0018 y enlaces nuevos cumplen la estructura. |
| Diff | `git diff --check` correcto. Se conservan y excluyen de publicación los cambios previos en `src/serial/sdk_adapter.py`, `src/shared_utils.py` y `src/web/controllers/channels_controller.py`. |
| Regresiones | Ocho casos nuevos aislados en `tests/test_web_authentication.py`, preparados pero no ejecutados. Cubren default, revocación, persistencia, constraints, API/query, CSRF/origen y proxy. |
| Suites y operación | Pytest/cobertura, Playwright y fuzzing no ejecutados. No se arrancaron servicios ni radio; la instalación y aceptación dinámica siguen pendientes de autorización de QA. Los contratos de tests anteriores de acceso público deberán revisarse durante esa aceptación, porque la API ahora exige autenticación. |

La publicación Git de esta entrega no equivale a un despliegue ni a una aceptación operativa.
