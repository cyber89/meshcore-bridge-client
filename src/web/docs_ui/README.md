# Visor OpenAPI local del candidato

Recursos propios Vanilla HTML/CSS/JS, sin paquetes Swagger UI/ReDoc ni CDN. El
servidor candidato sirve el shell en `/docs` y el alias `/redoc`, con estos recursos
exactos en `/docs/assets/docs.css` y `/docs/assets/docs.js`. El alias no afirma que
ReDoc esté instalado. Ninguna operación del catálogo está incrustada en el HTML.

Una acción manual obtiene `/openapi.json` mediante GET y, si se introdujo una
clave, la cabecera `X-Api-Key`. La clave no entra en la URL, el almacenamiento web,
cookies ni logs. El campo se vacía al iniciar la carga; la variable en memoria se
borra al cerrar el visor, abandonar la página o recibir HTTP 401/403. El visor
cierra cualquier contrato previo antes de cargar otro y cancela la solicitud en
curso al cerrar la documentación. No existe renovación automática, WebSocket,
temporizador ni botón para ejecutar las operaciones documentadas.

Descripciones, extensiones `x-*`, ejemplos y referencias se representan como
texto. Solo se resuelven referencias JSON Pointer locales, a un nivel, sin
descargar URLs externas. Se consultan rutas, métodos, grupos, autorización,
parámetros, cuerpos, respuestas, ejemplos, aliases documentados en extensiones y
componentes del JSON publicado por el candidato. La política efectiva de acceso
pertenece al middleware y a la ruta del esquema; un requisito OpenAPI representa
documentación, no autoriza una operación.

La inspección de esta fase es estática. No se ha abierto un navegador ni ejecutado
suites; accesibilidad, renderizado y flujo real de autenticación permanecen
pendientes de aceptación aislada autorizada.
