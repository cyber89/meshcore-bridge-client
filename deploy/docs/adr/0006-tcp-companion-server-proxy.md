# ADR 0006: Servidor Proxy TCP Companion Integrado para Multiplexación de Radio USB

- **Estado**: Aceptado
- **Fecha**: 2026-09-24
- **Autores**: Agente 0 (Lead Orchestrator & System Architect), Agente 2 (Bridge Architect)
- **Contexto**: `CONTEXT.md`, `reference/meshcore-proxy/`, `reference/meshcore_cli/`, `docs/ARCHITECTURE.md`

---

## Contexto y Problema

En un despliegue operativo habitual, el dispositivo transceptor LoRa MeshCore (ej. Heltec V3/V4, LilyGO T-Beam, RAK Wireless) está físicamente conectado mediante un único puerto serie USB (`/dev/ttyACM0` o `COMx`) al host.
El transceptor serie solo puede ser abierto por un único proceso del sistema operativo a la vez. Sin embargo, los operadores necesitan:
1. Mantener activo el puente continuo MQTT para automatizaciones IoT (n8n, Home Assistant).
2. Servir la interfaz web WebUI y WebSockets en tiempo real.
3. Conectar simultáneamente la aplicación móvil oficial de MeshCore (Android / iOS) vía Wi-Fi local para operadores en campo.
4. Conectar herramientas de línea de comandos (`meshcore-cli`) o scripts externos para diagnóstico o flasheo remoto.

En proyectos comunitarios previos, esto requería ejecutar un binario independiente externo (`meshcore-proxy`) que consumía puertos y procesos separados, o desconectar el bridge para usar la App móvil.

## Factores de Decisión

1. **Multiplexación de Medio Físico Único**: El bus serie UART no permite accesos concurrentes no coordinados sin corromper el delimitado de tramas binarias (`SOF 0xAA` / `EOF 0x55`).
2. **Compatibilidad con Clientes Oficiales**: La aplicación oficial de MeshCore para smartphones y el CLI oficial esperan comunicarse mediante un socket TCP en el puerto por defecto `5000`, enviando y recibiendo exactamente las mismas tramas binarias encapsuladas que se intercambian por el puerto serie USB.
3. **Consolidación en Proceso Único**: Ejecutar múltiples procesos en Linux aumenta el riesgo de fallos en cadena, orfandad de procesos o bloqueos mutuos si uno de ellos reinicia el puerto serie sin avisar a los demás.

## Decisión

Se decide implementar un **Servidor TCP Companion Proxy Integrado** (`TcpCompanionServer` en `src/tcp_companion_server.py`) ejecutado de forma nativa dentro del bucle de eventos `asyncio` del bridge:
1. **Escucha en Puerto Estándar (5000)**:
   - Se expone un servidor `asyncio.start_server` en el puerto configurable `5000` (configurable mediante variable de entorno `TCP_COMPANION_PORT`).
2. **Enrutamiento Bidireccional Asíncrono**:
   - Todo paquete binario recibido desde la radio LoRa se retransmite de forma transparente e instantánea a todos los clientes TCP conectados (modo broadcast de tramas).
   - Toda trama binaria emitida por un cliente TCP se inyecta en el serial driver respetando las colas de prioridad y guardas de airtime.
3. **Aislamiento de Sesión y Robustez**:
   - Cada cliente TCP conectado se aísla con tareas de lectura independientes (`StreamReader` / `StreamWriter`). Si un cliente se desconecta abruptamente, se cierran sus recursos sin perturbar el tráfico serie ni el broker MQTT.

## Consecuencias

- **Positivas**:
  - Interoperabilidad total e instantánea con la App oficial de MeshCore en smartphones (Android / iOS) sobre la red local Wi-Fi.
  - Compatibilidad completa con la suite CLI oficial (`meshcore-cli --host <ip> --port 5000`).
  - Cero dependencias de proxies o daemons externos; arquitectura unificada en un único proceso ejecutable.
  - Detección centralizada de saturación o abusos en la red local.
- **Negativas / Compensaciones**:
  - El host debe permitir la apertura del puerto TCP (requiere configurar reglas de firewall en `ufw` o router si se accede fuera de la subred local).
