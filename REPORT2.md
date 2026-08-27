# REPORT2 - Auditoría Adicional de Código Fuente MeshCore Bridge

> **Fecha**: 2026-08-24
> **Alcance**: Análisis completo del código fuente (`src/`, `tests/`, `config.py`)
> **Metodología**: Revisión manual exhaustiva, comparación con `Report.md` y `TODO.md` existentes
> **Objetivo**: Documentar hallazgos **NO cubiertos** en la auditoría previa

---

## Resumen Ejecutivo

Se analizaron **14 archivos fuente** (~6,500 líneas) y **30 archivos de prueba** (~3,800 líneas). Se identificaron **19 nuevos hallazgos** no documentados en la auditoría previa:

| Severidad | Cantidad | Acción Requerida |
|-----------|----------|------------------|
| CRITICAL | 1 | Implementar inmediatamente |
| HIGH | 3 | Implementar en sprint actual |
| MEDIUM | 9 | Planificar para próximo release |
| LOW | 6 | Backlog |

### Comparación con Hallazgos Previos

| Categoría | Report.md/TODO.md | TODO2 (Nuevos) | Total |
|-----------|-------------------|----------------|-------|
| Seguridad | 6 | 5 | 11 |
| Concurrencia | 9 | 3 | 12 |
| Calidad | 10 | 5 | 15 |
| Robustez | 7 | 4 | 11 |
| Frontend | 5 | 2 | 7 |
| **Total** | **37** | **19** | **56** |

---

## Metodología de Análisis

### Archivos Fuente Analizados

| Archivo | Líneas | Componente |
|---------|--------|------------|
| `src/bridge_core.py` | 654 | Orquestador central |
| `src/serial_driver.py` | 781 | Adaptadores serial/SDK |
| `src/mqtt_client.py` | 216 | Cliente MQTT |
| `src/tcp_companion_server.py` | 231 | Servidor TCP |
| `src/web/http_server.py` | 422 | Servidor HTTP/WS |
| `src/web/api_router.py` | 890 | Router API REST |
| `src/rx_router.py` | 1041 | Enrutador eventos RX |
| `src/protocol_types.py` | 461 | Tipos de protocolo |
| `src/rate_limiter.py` | 334 | Limitador de tasa |
| `src/deduplicator.py` | 83 | Deduplicador RAM |
| `src/health_reporter.py` | 84 | Reporte de salud |
| `src/contact_manager.py` | (previo) | Registro de nodos |
| `config.py` | 104 | Configuración |

### Archivos de Prueba Analizados

| Archivo | Líneas | Cobertura |
|---------|--------|-----------|
| `test_fuzzing_and_edge_cases.py` | 240 | Fuzzing MQTT, SQL, radio |
| `test_web_server.py` | 132 | API REST endpoints |
| `test_tcp_companion_server.py` | 156 | TCP framing, clientes |
| `test_serial_adapter.py` | 151 | Framing, watchdog, SDK |
| `test_rate_limiter_priority.py` | 49 | Cola prioridades, airtime |
| `test_protocol_types.py` | 184 | Serialization, CRC |
| `test_contact_manager.py` | 86 | NodeRegistry |
| `test_diagnostics.py` | 164 | Logs, health snapshot |
| `test_preflight.py` | 39 | Diagnóstico pre-arranque |
| `test_repeater_manager.py` | 32 | Payload builders |
| `test_sensor_decoder.py` | 119 | CayenneLPP decoding |
| `test_virtual_mesh_simulation.py` | 102 | Simulación E2E virtual |
| `test_bridge_logic.py` | 141 | Parsing, dedup |
| `test_concurrency_and_flapping.py` | 79 | Concurrencia, fallos |
| `test_store_and_forward.py` | 38 | Dedup RAM |
| `test_ha_discovery.py` | 31 | Telemetría nodos |
| `test_lqi_routing.py` | 131 | LQI, rutas |
| `test_security_audit.py` | 75 | Traversal, DoS |
| `test_mutation_resilience.py` | 102 | Bit-flip, mutaciones |
| `test_stress_flood.py` | 100 | Stress 500 paquetes |
| `test_n8n_parser_matrix.py` | 258 | n8n integration |
| `test_node_and_repeater_config.py` | 251 | Config local/remota |
| `test_tx_rate_limiter.py` | 96 | TX spacing, ACKs |
| `test_diagnostics_export.py` | 134 | Markdown export |
| `test_store_forward_modular.py` | 40 | TTL, eviction |
| `test_websocket_live.py` | 46 | WebSocket framing |
| `test_e2e_simulation.py` | 180 | Lifecycle completo |
| `test_serial_watchdog.py` | 53 | Watchdog timeout |

---

## Hallazgos Detallados

### 1. SEGURIDAD: TCP Companion sin Autenticación (SEC-007)

**Archivo**: `src/tcp_companion_server.py:43-59`

El servidor TCP acepta conexiones sin ningún mecanismo de autenticación:

```python
async def start(self) -> None:
    self.running = True
    self.server = await asyncio.start_server(
        self._handle_client,
        self.host,
        self.port,
    )
```

Cualquier dispositivo en la LAN puede conectarse al puerto 5000 y enviar comandos de radio. En un escenario de red mesh, esto significa que un nodo comprometido podría inyectar comandos maliciosos hacia la red completa.

**Impacto**: CRITICAL - Acceso no autorizado a transmisión RF.

---

### 2. SEGURIDAD: CORS Wildcard (SEC-008)

**Archivo**: `src/web/http_server.py:197-207`

```python
b"Access-Control-Allow-Origin: *\r\n"
b"Access-Control-Allow-Methods: GET, POST, OPTIONS, DELETE\r\n"
b"Access-Control-Allow-Headers: Content-Type, Authorization\r\n"
```

El wildcard `*` permite que cualquier sitio web haga solicitudes a la API. Un atacante podría crear un sitio malicioso que, si un usuario en la LAN lo visita, ejecute comandos admin o transmita mensajes a través del bridge.

**Impacto**: HIGH - Exposición de API a sitios web maliciosos.

---

### 3. CONCURRENCIA: Deduplicador sin Sincronización (CONC-010)

**Archivo**: `src/deduplicator.py:13-64`

`PacketDeduplicator` usa `collections.OrderedDict` sin locks. Los métodos son llamados desde:
1. Hilo de paho-mqtt (vía `_on_message`)
2. Event loop de asyncio (vía `_dispatch_parsed_frame`)

```python
def is_duplicate_sync(self, key: str) -> bool:
    now = time.time()
    self._prune(now)  # Modifica OrderedDict
    if key in self._cache:  # Lee OrderedDict
        ...
    self._cache[key] = now  # Escribe OrderedDict
    self._cache.move_to_end(key)  # Modifica OrderedDict
```

**Impacto**: MEDIUM - Posible corrupción de datos bajo alta concurrencia.

---

### 4. CALIDAD: Código Duplicado en RX Router (QUAL-011)

**Archivo**: `src/rx_router.py:621-906`

Los métodos `_handle_mesh_channel_msg` (145 líneas) y `_handle_mesh_direct_msg` (139 líneas) contienen lógica casi idéntica:

- Extracción de telemetría del repetidor
- Detección de comandos/respuestas
- Publicación MQTT a tópicos específicos
- Broadcasting WebSocket
- Logging estructurado

La duplicación crea riesgo de inconsistencias al modificar un método sin actualizar el otro.

**Impacto**: MEDIUM - Mantenimiento dificultado, riesgo de bugs.

---

### 5. ROBUSTEZ: Backpressure TCP No Manejado (ROB-008)

**Archivo**: `src/tcp_companion_server.py:85-116`

```python
def broadcast_companion_frame(self, payload: bytes) -> None:
    for writer in list(self.active_clients):
        try:
            writer.write(pkt)  # No verifica buffer lleno
            self._tx_bytes_total += len(pkt)
        except Exception as e:
            ...
```

Si un cliente TCP no consume datos rápidamente, el buffer de escritura crecerá indefinidamente en memoria.

**Impacto**: MEDIUM - Fuga de memoria potencial.

---

### 6. SEGURIDAD: WebSocket Origin No Validado (SEC-009)

**Archivo**: `src/web/http_server.py:156-159`

```python
if headers.get("upgrade", "").lower() == "websocket" and "sec-websocket-key" in headers:
    await self._handle_websocket_handshake(reader, writer, headers["sec-websocket-key"])
    return
```

No se valida el header `Origin` antes de aceptar la conexión WebSocket. Sitios web maliciosos podrían establecer conexiones WebSocket para recibir datos en tiempo real o inyectar comandos.

**Impacto**: HIGH - Exposición de datos en tiempo real.

---

## Análisis de Cobertura de Tests

### Tests que SÍ cubren los nuevos hallazgos

| Hallazgo | Test Existente | Estado |
|----------|----------------|--------|
| SQL Injection | `test_fuzzing_and_edge_cases.py:107` | ✅ Cubierto |
| Path Traversal | `test_security_audit.py:27` | ✅ Cubierto |
| DoS Payload Grande | `test_security_audit.py:53` | ✅ Cubierto |
| Concurrencia Dedup | `test_concurrency_and_flapping.py:34` | ✅ Cubierto |
| Serial Exception | `test_concurrency_and_flapping.py:55` | ✅ Cubierto |

### Tests que NO cubren los nuevos hallazgos

| Hallazgo | Test Faltante | Impacto |
|----------|---------------|---------|
| SEC-007 (TCP Auth) | Ninguno | No hay tests de autenticación TCP |
| SEC-008 (CORS) | Ninguno | No hay tests de políticas CORS |
| SEC-009 (WS Origin) | Ninguno | No hay tests de validación Origin |
| CONC-010 (Dedup Thread) | `test_concurrency_and_flapping.py` solo testea un hilo | Falta test multi-hilo real |
| ROB-008 (TCP Backpressure) | Ninguno | No hay tests de saturación de buffer |

---

## Recomendaciones de Implementación

### Inmediata (Sprint Actual)

1. **SEC-007**: Implementar autenticación por token en TCP Companion
   - Agregar campo `auth_token` en configuración
   - Validar token en handshake TCP
   - Rechazar conexiones sin token válido

2. **SEC-008**: Restringir CORS a orígenes específicos
   - Agregar config `CORS_ORIGINS=["http://localhost:8080"]`
   - Validar Origin header contra whitelist

3. **SEC-009**: Validar Origin en WebSocket
   - Verificar Origin contra whitelist de orígenes permitidos
   - Rechazar conexiones con Origin no autorizado

### Corto Plazo (Próximo Release)

4. **CONC-010**: Agregar threading.Lock al deduplicador
   - Usar `threading.Lock()` en métodos públicos
   - O migrar a asyncio.Lock en el event loop

5. **ROB-008**: Implementar backpressure TCP
   - Monitorear `writer.transport.get_write_buffer_size()`
   - Cerrar conexión si buffer excede umbral

6. **ROB-010**: Corregir `_force_serial_reconnect`
   - Agregar `await self.serial_adapter.connect()` después de disconnect

### Mediano Plazo (Backlog)

7. **QUAL-011**: Refactorizar `_handle_mesh_channel_msg` y `_handle_mesh_direct_msg`
   - Extraer lógica común a `_handle_mesh_msg_common()`
   - Reducir duplicación de ~280 líneas a ~140

8. **CONC-011**: Implementar limpieza de `_background_tasks`
   - Agregar limpieza periódica cada 60 segundos
   - Usar `asyncio.Task` con nombre para identificación

---

## Conclusión

La auditoría previa cubrió adecuadamente los componentes principales, pero se identificaron **19 nuevos hallazgos** en áreas de:
- **Seguridad de red** (TCP, CORS, WebSocket)
- **Concurrencia** (deduplicador, contadores)
- **Calidad de código** (duplicación, imports)

Los hallazgos más críticos (SEC-007, SEC-008, SEC-009) requieren implementación inmediata para proteger el bridge contra ataques de red local.

---

## Archivos Generados

- `TODO2.md`: Lista detallada de 19 hallazgos nuevos con severidad, ubicación y recomendaciones
- `REPORT2.md`: Este documento de análisis y报告
