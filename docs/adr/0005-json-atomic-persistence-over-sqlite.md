# ADR 0005: Persistencia Atómica en Archivos JSON sobre Base de Datos Relacional o SQLite

- **Estado**: Aceptado
- **Fecha**: 2026-09-24
- **Autores**: Agente 0 (Lead Orchestrator & System Architect), Agente 2 (Bridge Architect)
- **Contexto**: `CONTEXT.md`, `AGENTS.md` (Sección 1 y 2), `docs/ARCHITECTURE.md`

---

## Contexto y Problema

MeshCore Bridge opera como un puente de comunicaciones de misión crítica y bajo consumo diseñado para ejecutarse 24/7 en microcomputadoras de placa reducida (Single Board Computers - SBCs) como la **Orange Pi Zero 2W (512MB RAM)** o la **Raspberry Pi Zero 2 W**.
El sistema necesita persistir en almacenamiento permanente:
1. La libreta de contactos y directorio de nodos (`data/node_registry.json`).
2. La tabla de canales preconfigurados y claves PSK (`data/channels.json`).
3. El historial de consumo de tiempo de aire y duty cycle (`data/airtime_history.json`).

Existía el dilema de arquitectura entre adoptar un motor de base de datos SQL embebido (como SQLite con modo WAL) o mantener un esquema de serialización atómica en archivos JSON planos.

## Factores de Decisión

1. **Restricción de Recursos en Micro-SBCs**: Placas embebidas de bajo coste con 512 MB de memoria RAM total deben compartir memoria con el sistema operativo Linux, Mosquitto MQTT, Python runtime y buffers de radio. Motores de base de datos tradicionales incrementan la huella de memoria en 20-50 MB adicionales.
2. **Resiliencia ante Cortes Abruptos de Energía**: Nodos tácticos y estaciones base rurales operan con paneles solares o baterías auxiliares expuestas a caídas repentinas de tensión. Si una escritura en disco queda a medias, la base de datos corre riesgo de corrupción de cabecera o bloqueo de archivos de journal (`.db-wal` / `.db-shm`).
3. **Inspección Forense y Mantenimiento Fuera de Red**: En escenarios de emergencia fuera de red (*off-grid*), administradores sin herramientas complejas deben poder inspeccionar, editar, respaldar o reparar la configuración de canales y nodos utilizando comandos universales estándar (`cat`, `jq`, `grep`, `nano`) o editores de texto simples sin dependencias binarias.
4. **Volumen de Datos Acotado**: La especificación de MeshCore y la física de LoRa gestionan cientos de nodos o canales, no millones de registros transaccionales concurrentes.

## Decisión

Se adopta **Persistencia Atómica en Archivos JSON** mediante el patrón POSIX de *Write-and-Rename*:
1. **Escritura Atómica Segura**:
   - Todo volcado a disco escribe primero en un archivo temporal adyacente (`.tmp`) en el mismo sistema de archivos.
   - Se asegura la persistencia física en soporte magnético/flash mediante `flush()` y `os.fsync()`.
   - Se realiza un renombrado atómico sobre el archivo de destino mediante `os.replace(tmp_path, target_path)`. En sistemas compatibles con POSIX y Windows moderno, esta operación es atómica a nivel de sistema de archivos, garantizando que el archivo destino siempre es 100% íntegro (nunca queda truncado o a medio escribir).
2. **Caché en Memoria RAM para Lecturas Rápidas**:
   - Las lecturas de canales y nodos se resuelven en memoria RAM (estructuras `OrderedDict` y diccionarios indexados por clave pública) en tiempo $O(1)$ sin I/O de disco bloqueante en el bucle de eventos `asyncio`.
3. **Plantillas Desacopladas de Git**:
   - Los archivos de datos en caliente se ignoran en el control de versiones (`.gitignore`), suministrando plantillas limpias `*.json.example` para nuevas instalaciones limpias.

## Consecuencias

- **Positivas**:
  - Huella de memoria mínima (~45 - 65 MB de RAM para todo el proceso del bridge).
  - Cero corrupción de estado ante cortes abruptos de alimentación gracias a `os.replace`.
  - Máxima auditabilidad y portabilidad: copias de seguridad realizables con simple `cp` o `tar`.
  - Compatibilidad universal con herramientas de automatización n8n, Node-RED y scripts bash.
- **Negativas / Compensaciones**:
  - No apto para datasets de millones de filas con consultas relacionales complejas (no requerido en el dominio de redes LoRa Mesh).
  - La reescritura de todo el archivo para mutaciones pequeñas requiere mantener el número de nodos en rangos razonables (< 10,000 nodos).
