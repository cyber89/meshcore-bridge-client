---
name: web-browser-inspection
description: Inspección visual y funcional automatizada basada en Playwright (Chromium Headless). Captura screenshots en resoluciones Desktop (1920x1080) y Mobile (390x844), detecta excepciones JavaScript en consola, peticiones de red fallidas (4xx/5xx) y valida el renderizado del DOM en clientes web.
---

# Skill: Web Browser Inspection & Visual QA Automation

Esta habilidad proporciona capacidades automatizadas de inspección visual, funcional y de consola para aplicaciones web utilizando **Playwright** y **Chromium Headless**.

---

## Directiva Operativa Obligatoria

> [!IMPORTANT]
> Cada vez que implementes, refactorices o modifiques una vista, panel o componente web en `src/web/`:
> 1. Asegúrate de que el servidor web local esté ejecutándose (por ejemplo, en `http://localhost:8080`).
> 2. Ejecuta el script de inspección visual:
>    ```bash
>    python scripts/inspect_web.py --url http://localhost:8080
>    ```
> 3. Valida que el informe retorne `[PASS]`, sin excepciones de JavaScript no capturadas ni peticiones HTTP fallidas (4xx/5xx).
> 4. Inspecciona las capturas generadas en `tests/artifacts/desktop.png` y `tests/artifacts/mobile.png` antes de dar la tarea por completada.

---

## Capacidades y Funcionalidades del Inspector

1. **Navegación Headless Multi-Dispositivo**:
   - **Vista de Escritorio**: Resolución 1920x1080 (HD Desktop Viewport).
   - **Vista Móvil**: Resolución 390x844 (Viewport móvil tipo iPhone 14/15 con emulación táctil).
2. **Monitoreo Continuo de Consola y Red**:
   - Escucha y registro de `console.error` y `console.warn`.
   - Captura de excepciones JavaScript no controladas (`pageerror`).
   - Auditoría de códigos de respuesta HTTP (`status >= 400`).
3. **Generación de Artefactos de Calidad**:
   - `tests/artifacts/desktop.png`: Captura de pantalla de página completa en resolución de escritorio.
   - `tests/artifacts/mobile.png`: Captura de pantalla en vista responsive móvil.
   - `tests/artifacts/dom_dump.html`: Volcado completo del árbol DOM para validar componentes cargados.
4. **Reporte Estructurado**:
   - Resumen visual en consola y opción de salida JSON con `--json`.

---

## Formas de Ejecución

### Inspección Estándar (Salida en Consola):
```bash
python scripts/inspect_web.py --url http://localhost:8080
```

### Inspección con Salida JSON Estricta:
```bash
python scripts/inspect_web.py --url http://localhost:8080 --json
```

### Inspección con Directorio de Artefactos Personalizado:
```bash
python scripts/inspect_web.py --url http://localhost:8080 --output tests/artifacts/run_01
```
