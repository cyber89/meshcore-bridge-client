# ADR 0018: Autenticación de la estación personal

- **Estado**: Aceptado e implementado; aceptación dinámica pendiente
- **Fecha**: 2026-10-12

## Contexto y Problema

La estación personal necesita una cuenta web, sesión recordada por el navegador y cambio de usuario/contraseña. La protección anterior dependía de una API key opcional y permitía lecturas públicas. La solicitud inicial incluía un plazo total de tres minutos para introducir credenciales, con `admin:admin` como fallback. La evolución de esta misma fecha sustituye esa entrada durante instalación por una cuenta inicial fija y cambio obligatorio al entrar en la aplicación.

## Factores de Decisión

- Persistencia local SQLite existente, CPython 3.12+ y ausencia de un servidor de identidad externo.
- Proteger API completa y WebSockets además de la pantalla web.
- Evitar secretos en URLs o almacenamiento accesible a JavaScript.
- Revocación inmediata al cambiar credenciales y control CSRF para sesiones con cookie.
- Mantener instaladores Linux/Windows y preservar credenciales en upgrades.
- Conservar los controles propios de MQTT y TCP Companion sin transmitir por radio.

## Decisión

Cuenta única y hash scrypt con sal aleatoria, N=32768/r=8/p=3. Sesiones opacas en SQLite, cookie HttpOnly/SameSite=Strict/Secure en HTTPS y CSRF por cabecera. Recordar sesión durante 30 días o cookie de sesión con máximo de servidor de 12 horas. Un token Bearer independiente permite automatizaciones; la clave externa configurada continúa mediante cabecera y se rota separadamente.

Los instaladores comparten un helper Python que crea `admin:admin` únicamente si no existe una cuenta. No solicita credenciales ni espera un plazo de entrada. La cuenta inicial obliga a sustituir la contraseña antes de acceder a la estación; se conserva la posibilidad de cambiar el nombre de usuario. Actualizar o reinstalar conserva una cuenta existente, sus sesiones y su token generado. El login precede la inicialización de la SPA y sus peticiones. El botón **Perfil**, en la esquina superior derecha, abre la vista de cambio de credenciales y cierre de sesión. Véanse el [plan y contrato](../AUTHENTICATION_PLAN.md) y la [guía de despliegue](../DEPLOYMENT_GUIDE.md).

## Evolución del 2026-10-12

La decisión inicial implementó entrada de usuario y contraseña durante instalación, con un deadline de 180 segundos y fallback `admin:admin`. Por solicitud posterior del usuario se elimina esa interacción. La instalación sigue su flujo habitual y provisiona la cuenta pública inicial automáticamente; en el primer acceso, el backend y la SPA exigen cambiar la contraseña. Se conserva el bloqueo de la API privada, documentación OpenAPI, WebSockets y tokens de integración hasta completar el cambio, junto con los controles de CSRF y revocación existentes. La clave `BRIDGE_API_KEY` configurada también queda bloqueada mientras la cuenta inicial requiera cambio.

## Consecuencias

La API deja de ser pública; clientes deben suministrar sesión o token. Los secretos y respaldos SQLite requieren permisos protegidos. HTTP local permite compatibilidad, pero el transporte remoto requiere HTTPS. Cambiar credenciales cierra sesiones previas y revoca tokens generados; la clave de `.env` se administra independientemente. El valor público de arranque permite que quien acceda primero establezca la cuenta: la aplicación obliga a sustituirlo en el primer login antes de mostrar datos o ejecutar acciones de la estación.

No se añade tráfico LoRa, timers RF ni cambios en MQTT. La aceptación dinámica y de navegador queda pendiente hasta autorización explícita de suites conforme a AGENTS.md; el plan registra las comprobaciones estáticas de esta entrega.
