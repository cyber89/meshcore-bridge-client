# Revisión de CSS y estilos visuales — 2026-10-18

Se revisaron las siete vistas de la SPA sobre una estación virtual aislada, con
datos temporales, radio virtual y HTTP/WebSocket en puertos de loopback asignados
por el SO. La tarea no añade transmisiones, temporizadores ni cambios de radio.

## Correcciones

| Elemento | Problema reproducido | Resultado medido |
|---|---|---|
| Claves públicas (`code`) | Rosa del tema claro: 3,65:1 sobre el panel de metadatos | Token por tema; mínimo claro 6,20:1 |
| Contador de mensajes directos | Blanco sobre blanco: 1:1 | Superficie y texto neutrales; mínimo 6,03:1 |
| Etiquetas secundarias | 4,25:1 en tema claro | Superficie elevada compartida; mínimo 6,03:1 |
| Módulo de cada entrada de log | El color de énfasis claro se aplicaba a una consola oscura: 1,08:1 | Token propio de consola; mínimo 8,11:1 |
| Atribución del mapa | Leaflet sobrescribía el fondo oscuro al cargar después: 1,80:1 | Selector más específico, sin `!important`; mínimo 5,94:1 |

El texto del estado vacío de la consola comparte también un token adecuado para
su fondo oscuro. El alias `--bg-tertiary` apunta a la superficie elevada canónica;
la prueba existente detectó que en tema claro resolvía otro color de Bootstrap.
Se mantienen los componentes y la paleta general existentes.

## Evidencia

- Ejecución final conjunta: **25 aprobadas, 0 fallos, 0 errores, 0 skips** en
  274,59 s. JUnit: `tests/artifacts/css-review/final-stable.xml`.
- `tests/test_visual_styles_browser.py`: cinco pruebas de navegador aprobadas.
  Miden texto renderizado en 390×844 y 1920×1080, con temas oscuro y claro.
  Total: 3.130 muestras; mínimo 4,70:1; ninguna por debajo de 4,5:1.
- Se comprobaron controles táctiles de al menos 44×44 px en la cabecera y el chat,
  altura táctil de las subpestañas, foco visible y movimiento reducido.
- Las regresiones nuevas reprodujeron los fallos antes de corregir el CSS.
  El primer arreglo del mapa seguía empatando en especificidad con Leaflet;
  una segunda ejecución lo detectó y se corrigió el selector.
- `tests/test_frontend_ui_audit.py`: la espera de carga del tema acepta tanto
  el vendor original como su variante local, compatible con el trabajo existente.
  La prueba de tokens aprobó 54 combinaciones de texto y superficie.
- La ejecución conjunta inicial pasó las 25 comprobaciones pero registró un error
  intermitente de teardown por peticiones canceladas de analítica/airtime en la
  prueba de la paleta. La repetición aislada pasó. Se añadió una espera explícita
  del estado `aria-busy="false"` de analítica antes del reload de QA, conservando
  la detección estricta de peticiones fallidas.
- Build y `node scripts/build_frontend.cjs --check`: 31 assets sincronizados,
  incluidos CSS minimizado, gzip y hashes. Los artefactos preparados para Git
  se generan a partir del CSS del índice para excluir cambios locales ajenos.
- Ruff sobre los dos módulos de pruebas y mypy estricto sobre el módulo nuevo:
  sin errores.
- Capturas y mediciones: `tests/artifacts/visual-styles/` y
  `tests/artifacts/frontend-ui/`. Informes JUnit: `tests/artifacts/css-review/`.

Comando de navegador reproducible (desde la raíz, usando el entorno de QA):

```powershell
.venv/Scripts/python.exe -m pytest tests/test_visual_styles_browser.py tests/test_frontend_ui_audit.py -q --no-cov --basetemp tests/artifacts/css-review/reproduce
```

## Entorno y límites

Windows, CPython 3.12.14, pytest 9.1.1, Playwright 1.62.0, Node.js 24.19.0,
Ruff 0.16.3 y mypy 2.3.1. Se reutilizaron las herramientas locales, cuyas
versiones no coinciden en todos los casos con los pins de desarrollo actuales.
`pip check` detectó un conflicto preexistente: amqtt 0.12.0 pide websockets
15.0.1 y el entorno tiene 17.2. No se modificaron dependencias para esta tarea.

El sandbox bloqueó algunos sockets de `asyncio` al crear el event loop de
Windows; las ejecuciones finales usaron permiso de ejecución fuera del sandbox
manteniendo el servidor virtual en loopback. No se consultó ninguna estación
operativa ni broker externo.

Las teselas externas se sustituyen por imágenes locales neutrales. Esta evidencia
no valida cartografía en línea ni imágenes, gráficos canvas, pseudo-elementos,
todos los estados interactivos o conformidad WCAG completa. La suite de backend
y la cobertura global quedan fuera del alcance de esta revisión visual.

El checkout contenía cambios previos en frontend, autenticación, backend y
documentación. Se conservaron. Las pruebas describen ese checkout integrado;
el commit de esta tarea contiene exclusivamente los hunks propios y sus
artefactos correspondientes.
