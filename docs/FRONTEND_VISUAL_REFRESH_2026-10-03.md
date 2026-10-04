# Mejora visual del sitio y administración remota — 2026-10-03

## Resultado y alcance

Se aplica una paleta clara gris salvia, con texto oscuro y acentos azules, para reducir las grandes superficies blancas. Los componentes compartidos transmiten el cambio a navegación, chat, nodos, contactos, analítica, ajustes y diagnósticos. También se ajustan los diálogos generales, los diálogos de confirmación/aviso/entrada y la administración remota.

Base de implementación: `7a93028`. El trabajo de esta entrega modifica cuatro hojas CSS, sin cambios en JavaScript, endpoints, parámetros de radio, temporizadores ni dependencias de producción. Las implementaciones de diálogos y correcciones funcionales presentes en los commits anteriores pertenecen a trabajos previos; esta entrega mejora su presentación.

## Diseño aplicado

| Elemento | Cambio |
|---|---|
| Lienzo claro | `#dce3e4`, gris suave con un matiz verde/azul |
| Superficies | `#e7ecea`; capa elevada `#f1f3ee` |
| Texto y acentos | Colores ajustados también contra la superficie de hover; se conservan estados semánticos por rol/resultado |
| Chat, tarjetas y navegación | Fondos y sombras compartidos, burbujas y separadores sin blanco puro |
| Diálogos | Altura limitada al viewport dinámico, cuerpo desplazable, cabecera y pie separados, títulos que pueden partir líneas |
| Acciones | Botones de pie/cierre de al menos 44 px; botones de guardar remotos visibles con `position: sticky` |
| Formularios móviles | Campos de 16 px en modales, dos/tres columnas reducidas a una, acciones de ancho completo |
| Administración remota | Hasta 1080 px en escritorio, seis pestañas en dos filas de tres en móvil, autenticación desplazable, pie de guardado y terminal adaptados al tema |
| Movimiento y foco | Animaciones de modales/desbloqueo reducidas cuando se solicita; foco visible en pestañas y autenticación |

El blanco del contenedor de códigos QR se conserva para su lectura. No se añade un tema distinto ni una nueva opción de configuración.

## Coordinación y skills

El agente dirigente integra paleta, chat, cascada, contraste y documentación. El especialista frontend modifica diálogos y administración remota; después el dirigente revisa el diff e integra los tamaños responsive en la hoja cargada al final. Se utilizan `web-ui-design-system`, `html-css-modern-js` y `ui-ux-pro-max`, manteniendo Vanilla CSS y los selectores/contratos existentes. El análisis de configuración previo utilizó además especialistas backend/QA y protocolo; sus hallazgos se conservan en el [informe de configuración](NODE_CONFIGURATION_VERIFICATION_2026-10-03.md).

## Evidencia y límites de verificación

- Revisión estática: **82 pares de colores aprobados** con umbral 4,5:1: diez tokens de texto/acento sobre cuatro superficies en ambos temas, más texto blanco sobre ambos extremos del botón primario claro. La comprobación usa luminancia relativa sRGB de los colores hex declarados.
- Las cuatro hojas CSS tienen llaves equilibradas y `git diff --check` no informa errores. El equilibrio léxico no sustituye un parser CSS ni la inspección del estilo calculado.
- Se corrige una colisión de cascada: las reglas de tamaño remoto pasan a `admin.css`, cargada después de `components.css`. Así las reglas de escritorio no anulan los tamaños de tablet/móvil.
- La revisión automática de aprobación **rechazó** ejecutar la selección pytest/Chromium para esta mejora visual, por exigir autorización expresa de suites según `AGENTS.md`. Se solicitó autorización al usuario. La ejecución rechazada no comenzó.
- **No hay verificación renderizada ni capturas nuevas de esta mejora en esta entrega.** No se atribuyen a estos estilos las capturas o resultados de auditorías anteriores. Tampoco se certifica WCAG completo, comodidad visual individual o lectura/escritura de hardware.

Evidencia reproducible: [check_static.py](audits/frontend-visual-refresh-2026-10-03/check_static.py) y [static-results.json](audits/frontend-visual-refresh-2026-10-03/static-results.json). El JSON describe las hojas de trabajo sobre la base indicada, antes del commit de integración.

```powershell
.venv/Scripts/python.exe docs/audits/frontend-visual-refresh-2026-10-03/check_static.py
git diff --check
```

## Pasos para cerrar la comprobación visual

1. Con autorización expresa, ejecutar la selección mantenida de responsive, modales, contraste, teclado e idiomas con la fixture virtual de `tests/conftest.py`. Usa datos temporales, adaptador virtual y puerto de loopback asignado por el SO; bloquear dotenv y recursos externos según la política de QA.
2. Comprobar ES/EN y ambos temas en 320×740, 390×844, 768×1024 y 1920×1080: navegación, chat, nodos, contactos, analítica, ajustes y logs. Confirmar ausencia de scroll horizontal global, controles recortados o errores JS.
3. Revisar confirmación, aviso y entrada con textos largos, Escape, recorrido de foco y restauración al disparador. Confirmar que el pie se alcanza con viewport bajo y teclado móvil.
4. Revisar administración remota bloqueada y sesión autenticada simulada: seis pestañas, formularios largos, guardado visible, terminal y nombres largos. Incluir móvil en horizontal y zoom del navegador. Interceptar acciones administrativas; no transmitir RF.
5. Guardar capturas y resultados específicos de esta versión, inspeccionarlos visualmente y reparar cualquier regresión antes de afirmar que el layout está validado. Cerrar navegador, servidor y tareas en `finally`.

Esta mejora es visual: su implementación consume cero airtime y no crea spam, reintentos ni rearma timers. Las comprobaciones físicas de parámetros y los límites RF permanecen en el plan de configuración; requieren autorización y condiciones propias.
