# Observación actual del cliente oficial

Fecha de consulta: 2026-10-03, zona de referencia America/New_York.

Se abrió https://app.meshcore.nz/ en el navegador integrado de Codex, en segundo plano.
Tras activar su interfaz accesible, el árbol mostró `MeshCore Disconnected`,
`Not Connected`, `Connect a MeshCore device to continue.`, el botón `Connect`
y las pestañas `Contacts`, `Channels` y `Map`.
El menú desplegado mostró `Discover Contacts`, `Internet Map` y `Tools`.
No se conectó hardware ni se aceptaron permisos de USB/BLE.
Por tanto, esta observación no acredita el funcionamiento de formularios conectados.

Se abrió https://config.meshcore.io/ en otra pestaña temporal: el estado visible
fue `Repeater / Room server USB setup` y el botón `usb Connect`.
La lectura web del HTML público enumera controles de identidad/ubicación, acceso,
radio y funciones condicionadas por versión; ese HTML no equivale a una sesión
configuradora conectada. Es un flujo USB distinto de administrar un remoto por RF.

Fuentes primarias públicas leídas mediante la herramienta web durante esta tarea:

- https://docs.meshcore.io/cli_commands/: catálogo CLI; consultar diferencias
  RF/serial y funciones dependientes de build. La página viva no fija la revisión local.
- https://docs.meshcore.io/radio_presets/: presets mantenidos por la API del cliente;
  son sugerencias y no demuestran capacidades de una placa específica.
- https://blog.meshcore.io/2026/04/17/default-scope: descripción de la opción
  Experimental Settings del cliente y el alcance de los paquetes flood del Companion.
- https://github.com/meshcore-dev/meshcore: README oficial enlaza cliente web y
  configurador; explica gestión remota por LoRa desde el cliente móvil.

La apertura actual del PDF Quick Start no pudo completarse con la herramienta web.
Su lectura en la auditoría anterior permanece como evidencia histórica, no una
verificación nueva. No existe checkout del frontend del cliente oficial en las
referencias locales inspeccionadas. No se atribuye al cliente oficial el estado
interno observed/draft recomendado para el bridge.
