# Login visual y propuesta de recuperación local

Fecha: 2026-10-12. Trabajo coordinado entre un agente de diseño, un revisor de diseño/accesibilidad y un agente de seguridad. Este documento distingue cambios de interfaz implementados de la recuperación propuesta, que todavía no existe como comando ejecutable.

## Diseño de login

Mantener el estilo de la estación con sus tokens de `src/web/static/css/app.css`, su identidad vectorial local y sus temas claro/oscuro. Mejorar jerarquía, espaciado y legibilidad mediante un panel de identidad sobrio y un formulario sobre una superficie sólida. En móvil, una columna y desplazamiento propio evitan que el teclado o la altura de la pantalla oculten los controles.

Los controles conservan etiquetas visibles y foco de teclado. La contraseña puede mostrarse u ocultarse mediante un botón accesible y vuelve a ocultarse al terminar el intento de acceso. No se guarda en el almacenamiento del navegador. La ayuda de primera instalación se presenta de forma separada del formulario: `admin:admin` sigue exigiendo un cambio inmediato antes del acceso a datos.

No se modifican los contratos `/api/auth/*`, cookies, CSRF, sesiones recordadas, el botón Perfil o las restricciones de API/WebSocket. No hay una acción web para restablecer la contraseña. El diseño no añade tráfico RF, publicaciones MQTT ni servicios.

## Recuperación recomendada — propuesta pendiente de implementación

Para una estación personal, usar un comando local explícito disponible sólo para quien ya puede administrar la instalación mediante el sistema operativo. La autoridad es el acceso local/SSH autorizado al servidor y los permisos sobre la base de datos, no una sesión web ni el conocimiento de una contraseña por defecto.

Comando candidato, **todavía no implementado**:

```text
python scripts/reset_web_password.py --project-dir <directorio-de-instalacion>
```

El comando debe:

1. Resolver el directorio instalado y el mismo `DATABASE_PATH` que usa la estación. Rechazar rutas inválidas, enlaces simbólicos, base ausente o cuenta ausente; no crear otra instalación ni volver a `admin:admin`.
2. Ejecutarse con la identidad del servicio o el operador local propietario de la instalación. Conservar permisos y propietario de la base y sus sidecars. No cargar el núcleo, conectar hardware, arrancar servicios ni enviar paquetes.
3. Mostrar el nombre de cuenta actual y permitir conservarlo. Un cambio opcional de usuario utiliza la validación existente; puede ayudar si también se olvidó el nombre de usuario.
4. Pedir dos veces una contraseña nueva con entrada oculta. Mantener las reglas de 15–128 caracteres y máximo 1024 bytes UTF-8; no aceptar la contraseña por argumentos, variables de entorno, archivos de configuración, stdin redirigido ni logs. Fallar si no se puede garantizar entrada oculta; no utilizar el fallback con eco que documenta [getpass en Python 3.12](https://docs.python.org/3.12/library/getpass.html).
5. Actualizar sal/hash scrypt y generación de cuenta en una transacción SQLite; revocar todas las sesiones y tokens generados, y limpiar los contadores de intentos para que el nuevo login no quede bloqueado por intentos anteriores. Comparar dentro de la transacción la generación actual con la instantánea tomada antes de solicitar la contraseña y abortar si hubo un cambio concurrente.
6. No crear una sesión ni mostrar tokens. Pedir iniciar sesión normalmente desde el navegador con la contraseña nueva. La contraseña segura elegida durante recuperación no necesita volver a convertirse en una credencial temporal.

La revocación de sesiones después de una recuperación sigue la guía de [OWASP Forgot Password](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html). El uso de autoridad local y entrada de terminal es una decisión propuesta para esta estación, no una función documentada por OWASP como implementación de este proyecto.

La clave externa `BRIDGE_API_KEY` de `.env` conserva una administración independiente: no se revoca por eliminar los tokens generados en SQLite. Si hay sospecha de compromiso, el operador debe rotarla aparte y reiniciar la aplicación para aplicar la configuración. El comando no debe editar `.env` silenciosamente.

No incorporar un parámetro persistente como `RESET_PASSWORD=true`: podría seguir activo en futuros reinicios y devolver la estación a una contraseña conocida. Tampoco borrar la base SQLite para recuperar acceso: perdería chat, nodos, canales y timestamps de seguridad.

## Archivos previstos para implementar la recuperación

- `scripts/reset_web_password.py`: CLI local explícito y entrada oculta.
- `src/web/auth_store.py`: operación transaccional de recuperación sin sesión previa, utilizada exclusivamente por el CLI local.
- `tests/test_web_password_recovery.py`: regresiones aisladas de revocación, concurrencia, conservación de datos, permisos e interrupción antes de confirmar.
- Guía de despliegue y README: comandos concretos Linux/Windows y límites de recuperación.

La recuperación requiere una solicitud posterior de implementación. No se creó el script candidato ni se cambió ninguna contraseña de la instalación actual.

## Verificación de esta entrega

Se realiza revisión estática de HTML, referencias ARIA, traducciones, JS/CSS y activos minificados/gzip. La inspección de colores comprueba pares concretos de tokens; no acredita accesibilidad completa ni layout renderizado. Pytest, Playwright y fuzzing siguen suspendidos conforme a AGENTS.md. No se arranca una estación operativa para revisar el diseño.

La implementación visual conserva las rutas y los campos del login y Perfil. El módulo compartido `core/theme.js` aplica el tema guardado antes del login y conserva el comportamiento de la estación después de iniciar sesión. Se añade SVG decorativo local, ayuda de primera instalación desplegable, estados de carga y control de visibilidad de contraseña. La contraseña se oculta de nuevo después de un intento y al aceptar sesión.

La revisión independiente comprobó 17 IDs usados por autenticación, el tratamiento explícito de `hidden`, el scroll propio en `100dvh` y las áreas de controles. Corrigió un conflicto de cascada CSS que reducía el control de contraseña. Contrastes calculados para tokens reales:

| Par sobre superficie elevada | Oscuro | Claro |
| --- | --- | --- |
| Texto principal | 11,98:1 | 11,87:1 |
| Texto secundario | 7,40:1 | 5,12:1 |
| Borde de campo | 3,13:1 | 3,08:1 |
| Foco | 7,80:1 | 5,44:1 |

Texto blanco sobre botón primario `#2457d6`: 6,16:1. Son cálculos de estos pares concretos, sin renderizado ni certificación global WCAG.

Build y comprobación de 31 activos: 1.963.214 bytes servidos y 400.692 bytes gzip; tamaños de artefactos, no mediciones de runtime. Sintaxis JS y `git diff --check` correctos. El validador documental revisa 92 documentos y conserva los seis problemas de estructura preexistentes en ADR 0017. No se instalaron dependencias nuevas y no se ejecutaron suites ni servicios.
