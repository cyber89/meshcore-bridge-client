# MCP SSH de mantenimiento

Servidor stdio local para la estación autorizada `192.168.0.242`, usuario `root`.
No se registra automáticamente en Codex, no cambia configuración global y no abre
conexiones al importarlo o listar herramientas. Sus dependencias están separadas
de las del bridge y requieren Python >=3.10.

Instalar exclusivamente en un entorno local de mantenimiento y ejecutar con ese
intérprete:

```text
python -m pip install -r tools/ssh_mcp/requirements.txt
python tools/ssh_mcp/server.py
```

El cliente MCP debe lanzar el proceso stdio e inyectar en memoria las variables
`MESHCORE_SSH_HOST`, `MESHCORE_SSH_USER` y `MESHCORE_SSH_PASSWORD`. No escribir las
credenciales en archivos, argumentos de herramientas, logs o configuración MCP.

- `ssh_host_key`: negocia SSH sin autenticarse y devuelve el fingerprint SHA256.
  Descubrir la clave por la misma red no acredita por sí solo la identidad: cuando
  exista una clave conocida, compararla por un canal confiable.
- `ssh_execute`: recibe un comando explícito, un fingerprint `expected_host_key`
  (o `MESHCORE_SSH_HOST_KEY_SHA256` en el proceso), timeout 1–120 segundos y límite
  de salida 1–256 KiB. Comprueba la clave **antes** de enviar la contraseña.
  Los comandos son arbitrarios y pueden modificar la estación; el operador debe
  respetar el alcance autorizado y evitar TX, pings y cambios de radio. El host
  necesita `timeout` de GNU coreutils. Un comando que se daemoniza puede sobrevivir
  al timeout; cerrar el canal tampoco garantiza terminar todos sus descendientes.
- `ssh_upload_file`: SFTP de un archivo absoluto bajo el workspace, máximo 100 MiB,
  hacia un archivo nuevo en un directorio staging existente
  `/tmp/meshcore-staging-*` o `/opt/meshcore-staging-*`. Rechaza rutas operativas,
  `.env`, credenciales de configuración, symlinks remotos y miembros peligrosos
  de archivos tar. Un archivo parcial puede permanecer si falla la transferencia.
  El SHA256 retornado corresponde al archivo **local**; verificar el remoto antes
  de extraerlo. Crear el directorio staging con permisos 0700 mediante una acción
  explícita previa. Preferir `git archive` de un commit publicado.

No se transmiten paquetes de radio automáticamente. La redacción de salidas es
heurística: oculta la contraseña SSH exacta, campos con nombres de credenciales y
bloques PEM de claves privadas; no garantiza identificar texto libre, secretos
codificados, archivos con nombres inesperados ni contenidos de archivos binarios.
Seleccionar comandos que omitan secretos desde el origen y revisar resultados
antes de guardarlos. Evitar `cat .env`, dumps completos de configuración y logs
con mensajes privados. Los comandos no se incluyen en los resultados del MCP.

Bloqueos Paramiko y SFTP se ejecutan mediante `asyncio.to_thread`; cada operación
cierra canales, transport y sockets. No hay conexiones persistentes, retries,
timers de radio ni cambios del servicio al arrancar el MCP. La cancelación del
cliente no detiene instantáneamente un thread ya iniciado; los límites de red y
comando siguen aplicándose.

Fuentes primarias: [SDK MCP v1 y FastMCP](https://py.sdk.modelcontextprotocol.io/v1/),
[Transport Paramiko](https://docs.paramiko.org/en/stable/api/transport.html),
[SFTP Paramiko](https://docs.paramiko.org/en/stable/api/sftp.html).
La dependencia `mcp<2` conserva la API FastMCP de la línea v1; no usa el paquete
FastMCP de terceros ni instala CLI extras.
