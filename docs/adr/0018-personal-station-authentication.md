# ADR 0018: Autenticación de la estación personal

- **Estado**: Aceptado e implementado; aceptación dinámica pendiente
- **Fecha**: 2026-10-12

## Contexto y Problema

La estación personal necesita una cuenta web creada durante instalación, sesión recordada por el navegador y cambio de usuario/contraseña. La protección anterior depende de una API key opcional y permite lecturas públicas. El usuario solicita un plazo total de tres minutos para introducir credenciales, con `admin:admin` como fallback.

## Factores de Decisión

- Persistencia local SQLite existente, CPython 3.12+ y ausencia de un servidor de identidad externo.
- Proteger API completa y WebSockets además de la pantalla web.
- Evitar secretos en URLs o almacenamiento accesible a JavaScript.
- Revocación inmediata al cambiar credenciales y control CSRF para sesiones con cookie.
- Mantener instaladores Linux/Windows y preservar credenciales en upgrades.
- Conservar los controles propios de MQTT y TCP Companion sin transmitir por radio.

## Decisión

Cuenta única y hash scrypt con sal aleatoria, N=32768/r=8/p=3. Sesiones opacas en SQLite, cookie HttpOnly/SameSite=Strict/Secure en HTTPS y CSRF por cabecera. Recordar sesión durante 30 días o cookie de sesión con máximo de servidor de 12 horas. Un token Bearer independiente permite automatizaciones; la clave externa configurada continúa mediante cabecera y se rota separadamente.

Los instaladores comparten un helper Python con deadline monotónico total de 180 segundos y entrada oculta de contraseña. El fallback solicitado obliga a cambiar credenciales antes de acceder a la estación; actualizar no reinicia la cuenta. El login precede la inicialización de la SPA y sus peticiones. Véanse el [plan y contrato](../AUTHENTICATION_PLAN.md) y la [guía de despliegue](../DEPLOYMENT_GUIDE.md).

## Consecuencias

La API deja de ser pública; clientes deben suministrar sesión o token. Los secretos y respaldos SQLite requieren permisos protegidos. HTTP local permite compatibilidad, pero el transporte remoto requiere HTTPS. Cambiar credenciales cierra sesiones previas y revoca tokens generados; la clave de `.env` se administra independientemente. El valor público de arranque permite que quien acceda primero establezca la cuenta: debe sustituirse al instalar o en el primer login.

No se añade tráfico LoRa, timers RF ni cambios en MQTT. La aceptación dinámica y de navegador queda pendiente hasta autorización explícita de suites conforme a AGENTS.md; el plan registra las comprobaciones estáticas de esta entrega.
