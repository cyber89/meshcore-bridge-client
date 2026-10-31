# ADR 0026: Modularización de Telemetría RX y Validadores Administrativos

- **Estado**: Aceptado
- **Fecha**: 2026-10-31
- **Autores**: Lead Orchestrator & System Architect
- **Contexto**: Fase 4 del Plan de Corrección Backend (`auditoria_backend_y_plan_correccion.md`), `src/rx_router.py`, `src/routers/telemetry_processor.py`, `src/admin/local_config_executor.py`, `src/admin/validators/`

---

## Contexto y Problema

Durante la auditoría integral del backend, dos componentes clave de procesamiento y administración presentaron una concentración crítica de complejidad ciclomática (CC) y responsabilidades mixtas:

1. **`LocalConfigExecutor` (Capa de Administración)**:
   - El método `_prevalidate_local_params` superaba las 180 líneas continuas con una Complejidad Ciclomática de McCabe de **CC = 93**.
   - Validaba en un único bloque monolítico tipos, rangos numéricos, límites físicos de radiofrecuencia (410..930 MHz, -9..30 dBm, BW, SF, CR), coordenadas geográficas GPS (finitud, no-NaN, rangos de latitud y longitud), cadenas UTF-8 sin caracteres de control para identidad y posición, políticas de ciclo de trabajo/airtime de host y modos numéricos de telemetría.
   - Cualquier error en la validación de un parámetro secundario podía impactar de forma no determinista la aplicación de parámetros críticos de radio.

2. **`RxEventRouter` (Capa de Dominio de Malla y Enrutamiento)**:
   - Superaba las 1,600 líneas de código.
   - Además de enrutar eventos entrantes hacia sus respectivos manejadores (`AdvertHandler`, `ContactHandler`, `MeshMessageHandler`, `RepeaterAdminHandler`), concentraba más de 300 líneas dedicadas exclusivamente al procesamiento de telemetría de malla y sincronización de estado de la estación base local:
     - Normalización y decodificación de payloads de telemetría (batería, voltaje, Cayenne LPP).
     - Extracción y validación de coordenadas de posición fija o GPS.
     - Cálculo de LQI instantáneo (`LinkQualityEngine.compute_instant_lqi`) a partir de RSSI, SNR y saltos observados.
     - Sincronización y actualización de las propiedades del nodo local (`SELF_INFO`) en el registro de nodos.
     - Estructuración y publicación de telemetría enriquecida hacia el broker MQTT para n8n y Home Assistant.

## Factores de Decisión

1. **Reducción Drástica de Complejidad Ciclomática (SOLID / Clean Code)**:
   - Disminuir la CC de `_prevalidate_local_params` a valores estándar de la industria (CC < 10, preferentemente CC < 5), delegando en funciones puras y cohesivas de validación.
2. **Cohesión de Dominio en Telemetría**:
   - Separar el enrutamiento puro de eventos de la lógica profunda de cálculo de calidad de enlace (LQI), decodificación sensorial y sincronización de hardware local.
3. **Preservación Incondicional de Contratos Públicos**:
   - `LocalConfigExecutor` debe mantener su firma `execute(data)` y sus métodos de validación de alto nivel.
   - `RxEventRouter` debe mantener los métodos `_handle_mesh_telemetry_msg` y `_handle_local_station_telemetry` accesibles para fixtures y pruebas existentes.

---

## Decisión

Se implementa la extracción y desacoplamiento de ambos subsistemas:

### 1. Extracción de `TelemetryProcessor` (`src/routers/telemetry_processor.py`)

Se crea la clase `TelemetryProcessor`, la cual asume la responsabilidad exclusiva de procesar, normalizar y reportar métricas de telemetría:

1. **Procesamiento de Telemetría de Malla (`process_mesh_telemetry`)**:
   - Extrae métricas de radiofrecuencia (RSSI, SNR, saltos de paquete).
   - Calcula el LQI instantáneo mediante `LinkQualityEngine.compute_instant_lqi(rssi, snr, hops)`.
   - Normaliza lecturas de batería, voltaje, temperatura y canales analógicos.
   - Integra coordenadas geográficas (`get_coord`, `location_pair`) y actualiza la presencia y posición del nodo emisor en `NodeRegistry`.
   - Publica el payload estructurado normalizado en el tópico MQTT correspondiente (`meshcore/telemetry/<pubkey>`).

2. **Sincronización de Telemetría Local (`process_local_station_telemetry`)**:
   - Procesa la información de autodiagnóstico de la radio host (`SELF_INFO`).
   - Sincroniza la clave pública local, el nombre del nodo y las lecturas de telemetría interna con la base de datos de la estación y los clientes WebSocket.

3. **Fachada `RxEventRouter` ([`src/rx_router.py`](../../src/rx_router.py))**:
   - Instancia o recibe `TelemetryProcessor` y delega limpiamente sus llamadas:
     ```python
     def _handle_mesh_telemetry_msg(self, data: dict[str, Any], raw_text: str) -> None:
         self.telemetry_processor.process_mesh_telemetry(data, raw_text)

     def _handle_local_station_telemetry(self, data: dict[str, Any]) -> None:
         self.telemetry_processor.process_local_station_telemetry(data)
     ```
   - El paquete `src/routers/` reexporta `TelemetryProcessor`, `get_coord` y `location_pair` para acceso transparente.

---

### 2. Módulo de Validadores Administrativos (`src/admin/validators/`)

Se descompone la validación monolítica de configuración local en un paquete especializado de validadores de responsabilidad única:

1. **`schema.py` ([`src/admin/validators/schema.py`](../../src/admin/validators/schema.py))**:
   - Define la excepción canónica `LocalConfigValidationError`.
   - Define constantes de atributos admitidos (`ALLOWED_LOCAL_KEYS`, `OTHER_PARAM_FIELDS`, `UNSUPPORTED_LOCAL_FIELDS`).
   - Implementa `validate_general_schema`, asegurando que no existan campos no soportados o estructuras mal formadas.

2. **`radio_params_validator.py` ([`src/admin/validators/radio_params_validator.py`](../../src/admin/validators/radio_params_validator.py))**:
   - `validate_radio_params`: Valida rangos de potencia TX (-9..30 dBm), frecuencias LoRa admitidas (410..930 MHz), anchos de banda (BW), factores de ensanchamiento (SF 7..12) y tasas de código (CR 5..8).
   - `validate_tuning_params`: Valida parámetros de afinamiento de hardware (`rx_delay`, `af`).

3. **`location_validator.py` ([`src/admin/validators/location_validator.py`](../../src/admin/validators/location_validator.py))**:
   - `validate_location_params`: Valida la finitud y rangos de latitud (-90..90), longitud (-180..180) y altitud, así como el flag de posición fija (`fixed_position`).

4. **`identity_validator.py` ([`src/admin/validators/identity_validator.py`](../../src/admin/validators/identity_validator.py))**:
   - `validate_identity_params`: Valida longitud UTF-8 (máximo 31 bytes para el nombre), ausencia de caracteres de control o saltos de línea, información de propietario (`owner_info`), PIN de dispositivo y modo de hashing de ruta (`path_hash_mode`).
   - `validate_custom_var`: Valida nombres y valores de variables personalizadas de firmware.

5. **`airtime_policy_validator.py` ([`src/admin/validators/airtime_policy_validator.py`](../../src/admin/validators/airtime_policy_validator.py))**:
   - `validate_airtime_policy_params`: Valida políticas de ciclo de trabajo (`duty_cycle_limit_pct`), umbrales de advertencia y corte (`warn_threshold_pct`, `airtime_cutoff_*`), y retardos de pre-envío hacia repetidores.
   - `validate_telemetry_modes`: Valida modos numéricos de telemetría base, de ubicación y ambiental.

6. **Refactorización de `LocalConfigExecutor` ([`src/admin/local_config_executor.py`](../../src/admin/local_config_executor.py))**:
   - El método `_prevalidate_local_params` se reduce a una secuencia lineal y limpia de llamadas delegadas:
     ```python
     validate_general_schema(candidate)
     validate_radio_params(candidate, final_config)
     validate_tuning_params(candidate)
     validate_location_params(candidate, final_config)
     validate_identity_params(candidate)
     validate_airtime_policy_params(candidate)
     validate_telemetry_modes(candidate)
     ```
   - **Resultado**: La Complejidad Ciclomática disminuyó de **93 a < 5**, garantizando total legibilidad, aislamiento de fallos y mantenibilidad a largo plazo.

---

## Consecuencias y Beneficios

1. **Métricas de Código de Grado Profesional**: La mayor fuente de complejidad ciclomática del backend fue erradicada, situando el método de validación dentro de los estándares más rigurosos de Clean Code.
2. **Encapsulamiento del Cálculo de LQI**: Cualquier ajuste en los coeficientes de suavizado EMA o en la fórmula de calidad de enlace queda confinado en `TelemetryProcessor` y `LinkQualityEngine`, sin riesgo de efectos secundarios en el enrutamiento de paquetes de texto o administración.
3. **Validación Determinista y Reutilizable**: Los validadores pueden ser consumidos de forma independiente por el endpoint REST `POST /api/config/local`, por el despachador de tópicos MQTT `LocalConfigExecutor` o por utilidades CLI.
4. **Verificación Automatizada**: Todas las suites de pruebas administrativas (`test_admin_executors.py`, `test_admin_executor_type_boundaries.py`) y de enrutamiento (`test_rx_event_router.py`, `test_lqi_engine.py`, `test_sensor_decoder.py`) continúan pasando al 100% sin requerir adaptaciones en sus aserciones.
