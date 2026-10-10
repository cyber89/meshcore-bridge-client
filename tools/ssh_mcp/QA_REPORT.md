# Verificación aislada de MCP 2 y Paramiko 5

Fecha: 2026-10-10. Entorno separado de la aplicación:
`artifacts/python315-upgrade/ssh-env`, CPython 3.15.0 estable, Windows 11 AMD64.
No se ejecutó el servidor stdio, no se registró un MCP global y no se abrió SSH
contra la estación autorizada ni otro destino operativo.

## Dependencias y migración

- SDK oficial `mcp==2.3.0` y `paramiko==5.0.0`, fijados en el manifiesto propio.
- Resolución local: `httpx2==2.13.1`, `pytest==9.1.1`, `ruff==0.17.0`.
  El entorno del bridge con HTTPX 0.28 no se modificó para instalar estos paquetes.
- El import antiguo `mcp.server.fastmcp.FastMCP` produjo el error esperado con
  MCP 2. El [SDK oficial](https://py.sdk.modelcontextprotocol.io/migration/)
  documenta el cambio a `mcp.server.mcpserver.MCPServer`. Se conservaron los
  decoradores `tool()` y el transporte stdio.
- [Paramiko 5](https://www.paramiko.org/changelog.html) retira algoritmos SHA1 y
  GSS. No se habilitaron alternativas retiradas. Las llamadas actuales a Transport,
  autenticación con contraseña sin fallback y SFTP conservan sus interfaces.
- El hash de archivos usa `hashlib.file_digest`; las regresiones comparan el
  resultado sobre bytes binarios con SHA256 esperado.

## Evidencia

| Comprobación | Resultado |
| --- | --- |
| Prueba previa a migración | Un error reproducido: `ModuleNotFoundError` al importar FastMCP con el SDK 2.3.0. |
| Pytest propio, después de migración | 10 passed en 1.57 s; exit 0. |
| Pytest propio con guarda de runtime | 15 passed en 1.48 s; exit 0. Incluye las diez regresiones anteriores y cinco rechazos de runtime. |
| Ruff propio | All checks passed; exit 0. |
| `pip check` del entorno separado | No broken requirements found; exit 0. |
| `git diff --check` de los archivos propios | Sin errores de espacios; exit 0. |

Comandos con el Python de ese entorno:

```text
python -m pytest -c tools/ssh_mcp/tests/pytest.ini tools/ssh_mcp/tests/test_maintenance.py -q
python -m ruff check tools/ssh_mcp/server.py tools/ssh_mcp/tests/test_maintenance.py
python -m pip check
```

Las pruebas deniegan `socket.create_connection` por defecto, limpian las variables
SSH operativas y sustituyen los transportes por dobles. Cubren registro y salida
estructurada MCP, fingerprint antes de autenticación, cierre de transportes,
salida acotada/redactada y rechazo de rutas o tar operativos.

La ampliación del baseline reprodujo primero el fallo de la nueva regresión:
Python 3.10 simulado llegaba a importar Paramiko. Ahora una guarda independiente
de biblioteca estándar exige `sys.implementation.name == "cpython"`, versión
`>= (3, 15, 0)` y `releaselevel == "final"` antes de importar los SDK y construir
`MCPServer`. Rechaza 3.10 final, 3.14 final, 3.15 RC, 3.16 alpha y otro intérprete
simulados sin llegar a imports externos; no carga `config.py` ni `.env` del bridge.
Las pruebas de runtime simulan sus metadatos en CPython 3.15.0: no equivalen a
ejecutar suites completas bajo esos intérpretes anteriores.

La primera ejecución después del cambio se bloqueó al crear el self-pipe del
event loop de Windows: `socket._fallback_socketpair -> accept`, antes del body
asíncrono. Se detuvo y repitió permitiendo el loopback interno de asyncio; las
guardas SSH se mantuvieron. No se cambiaron expectativas para aprobar la prueba.

El launcher emitió una advertencia de ubicación real del runtime embebido en las
comprobaciones sin escalación. Los comandos registraron la versión 3.15.0 y los
resultados indicados; esta evidencia no certifica una instalación de host general.
No se ejecutaron mypy, cobertura o navegador para esta herramienta independiente.
Los dobles no acreditan negociación SSH real, compatibilidad de algoritmos de una
estación específica, comportamiento remoto de coreutils ni integridad del archivo
SFTP recibido. Esas comprobaciones requieren una autorización operativa separada.
