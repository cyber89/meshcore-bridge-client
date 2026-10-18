# Auditoría de login — 2026-10-12

## Solicitud y alcance

El usuario autoriza ejecutar una versión local y visitarla con navegador para comprobar uniformidad, adaptación a tamaños de pantalla sin scroll en los tamaños auditados, colores, tipografía y validación de entradas. Define contraseñas nuevas de **8–64 caracteres, sin complejidad**.

Equipo: backend/seguridad para política y contratos; frontend para reproducción real y corrección de layout; QA para pruebas mantenidas, aislamiento y revisión independiente. El principal integra documentación, evidencia y publicación.

El navegador se conecta a FastAPI/Uvicorn real sobre loopback y puerto asignado por el sistema operativo. La estación utiliza SQLite y configuración temporales, VirtualMeshAdapter y MQTT simulado. No se utiliza una estación en `localhost:8080`, hardware RF ni broker de producción. Los procesos y contextos tienen limpieza mediante fixtures/finally.

## Plan de auditoría

1. Ejecutar la matriz de pantallas y estados antes de corregir el login. Medir dimensiones reales de scroll y revisar capturas; comprobar estilos calculados, foco y áreas táctiles.
2. Escribir y ejecutar regresiones de la política de contraseñas, observar los fallos esperados y actualizar backend/OpenAPI/frontend de forma consistente.
3. Corregir causas de cascada CSS y composición del layout, preservando contenido funcional y campos visibles. No ocultar desbordamiento como sustituto de adaptación.
4. Ejecutar nuevamente navegador, pruebas de autenticación, suite mantenida y análisis estáticos. Registrar fallos, skips y limitaciones reales, sin convertir un resultado parcial en una suite aprobada.

## Hallazgos reproducidos

El baseline real de navegador detectó desbordamiento vertical al desplegar ayuda y errores: altura de contenido aproximada de 833 px en 1366×768, 915 px en 390×844 y 869 px en 640×360. Las capturas iniciales mostraron campos y ayuda fuera de la pantalla en móvil y landscape. La causa combina padding alto, acumulación vertical y ausencia de una composición específica para pantallas bajas.

Una regla general de `.form-group input[type="password"]` tenía mayor especificidad y alteraba altura/fondo/padding del campo de contraseña. Además, el gradiente de Bootswatch sobre el botón primario impedía mostrar el relleno canónico esperado. Estas diferencias se detectaron en captura y estilos calculados, no sólo mediante búsqueda de variables en CSS.

Las fixtures antiguas de navegador cargaban la SPA sin autenticación. Se adapta el entorno de QA para iniciar sesión por la API real y compartir la cookie con el contexto del navegador; no se omite el middleware. Las pruebas propias del primer acceso mantienen una cuenta inicial sin modificar para comprobar el cambio obligatorio.

## Política de entradas

Las contraseñas nuevas cuentan caracteres Unicode/puntos de código: 8 y 64 son válidos; 7 y 65 se rechazan. No hay requisitos de mayúsculas, números o símbolos ni recorte silencioso de espacios. El frontend debe contar con `Array.from`, evitando que los atributos nativos basados en UTF-16 rechacen 64 caracteres de plano suplementario que acepta Python.

Login y contraseña actual conservan el límite previo de hasta 128 caracteres para permitir `admin:admin` y credenciales ya existentes. Esa compatibilidad no cambia la política de creación o modificación. La cuenta inicial continúa restringida hasta cambiar la contraseña. Nombre de usuario: 1–64 letras ASCII, dígitos, puntos, guiones o guiones bajos. Se rechazan tipos JSON inválidos, y los errores de validación no persisten una actualización parcial.

## Entorno y evidencia

CPython local 3.12.14 sobre Windows 11 AMD64. Se reutiliza la venv del proyecto para QA. La colección inicial encontró `httpx` ausente; se instaló `httpx==0.28.1` como dependencia de QA local. El `pip check` detecta el conflicto preexistente entre `amqtt==0.12.0` y `websockets==17.2`; no se modifica una dependencia de producción ajena a esta auditoría para ocultarlo.

Las capturas y resultados detallados se conservan en `tests/artifacts/login-audit/` y `tests/artifacts/login-audit-20261012-qa/`, ignorados por Git. Los resultados finales de la matriz y las suites se añaden al cerrar la revisión.
