# ADR 0011: Preparación gradual de FastAPI con servidor actual conservado

- **Estado**: Preparación autorizada e iniciada; adopción de producción condicionada
- **Fecha**: 2026-10-08
- **Autores**: Líder e investigadores de backend, contratos, seguridad e instalación
- **Base**: `457903d` y árbol de trabajo existente

## Contexto y Problema

[PROYECTO.md](../../PROYECTO.md) propone migrar el transporte web a FastAPI.
El servidor actual integra HTTP, WS y estáticos; el router conserva contexto,
canales, historiales y mapas utilizados también por el core. La migración no puede
duplicar el bridge ni romper contratos REST/WS o instalar dependencias por sorpresa.
El usuario pidió comenzar las fases secuencialmente y continuar sin suites.

## Factores de Decisión

- Python 3.10 mínimo, headless y dependencias opcionales.
- Paridad REST/WS/SPA y propiedad única de radio, MQTT y estado de negocio.
- Señales del core y límite actual de cierre por subsistema de 1,5 s.
- Evidencia binaria de seis destinos, separada de evidencia operativa ausente.
- Cambios anteriores en el checkout que deben conservarse fuera de esta entrega.

## Decisión

Preparar un seam neutral y un adaptador ASGI opcional usando FastAPI 0.143.0,
Uvicorn 0.54.0, Pydantic 2.14.0 y websockets 16.1.1. Declarar esos candidatos en
el extra `web`, sin activar ASGI en la fábrica del bridge. Diferir imports concretos
del servidor actual y conservar exports de compatibilidad. La fábrica ASGI recibirá
el router existente; no creará radio, MQTT o schedulers.

El servidor actual continúa siendo el predeterminado. El adaptador inicial no
contiene endpoints de negocio, WS ni SPA; no se ofrece como sustituto operativo.
Seguridad perimetral, DTO, rutas, WS, documentación e instaladores se trasladarán
en las fases de [PROYECTO.md](../../PROYECTO.md), conservando sus puertas.

No ejecutar suites por instrucción expresa del usuario. Lectura de fuentes,
análisis sintáctico y revisión de metadatos documentan preparación; no reemplazan
las puertas de ejecución para adoptar o retirar un servidor.

## Consecuencias

El core conserva estado y lifecycle; headless puede evitar imports del servidor
concreto, aunque la ausencia de imports transitivos aún requiere comprobación en
ejecución. Los manifiestos opcionales permiten preparar integración futura sin
alterar la instalación habitual. Temporalmente hay dos adaptadores; sólo el actual
está conectado al core. Las bibliotecas candidatas no se instalaron en su entorno.

Riesgos de señales, bind, lifespan, cancelación y cierre quedan registrados en los
[contratos internos](../fastapi/INTERNAL_CONTRACT_BASELINE.md) y el
[informe de fase 1](../fastapi/PHASE_1_REPORT.md). La aceptación de producción
queda pendiente de paridad y verificación autorizada; no se aprueba por disponer
de wheels ni por publicar esta preparación.
