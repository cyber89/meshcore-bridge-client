# ADR 0007: Desacoplamiento y Filtrado Estricto de Telemetría y Balizas del Nodo Local (Estación Base Host)

- **Estado**: Aceptado
- **Fecha**: 2026-09-24
- **Autores**: Agente 0 (Lead Orchestrator & System Architect), Agente 2 (Bridge Architect), Agente 4 (Web UI/UX Architect)
- **Contexto**: `CONTEXT.md`, `AGENTS.md` (Sección 1.1 y Checklist de Impacto en Malla), `docs/ARCHITECTURE.md`

---

## Contexto y Problema

El transceptor de radio conectado físicamente por USB a la máquina anfitriona (Host) actúa como la **Estación Base Local** (`LOCAL_NODE`).
En versiones tempranas y en herramientas de terceros, ocurrían tres anomalías arquitectónicas graves:
1. **Contaminación de la Libreta de Contactos**: El transceptor local aparecía listado a sí mismo como un "contacto remoto" en la interfaz de usuario, permitiendo que el operador intentara enviarse mensajes a su propia clave pública.
2. **Bucle de Retroalimentación y Tormenta de Paquetes (*Loopback Storm*)**: Cuando el nodo local emitía un paquete o baliza por radio, el receptor del propio transceptor lo escuchaba y lo reinyectaba en el bus asíncrono, provocando eco infinito y saturación total del airtime LoRa.
3. **Telemetría y Métricas Ficticias en la UI**: El nodo local se alimenta de forma continua a 5V mediante el bus USB del SBC/PC; sin embargo, la interfaz renderizaba chips de batería erráticos (ej. 36%, 100% o `--%`), así como estadísticas de RF simuladas (`📡 Local`, `📶 Local`, `🔀 0 hops`, `LQI: 100%`) que confundían al operador.

## Factores de Decisión

1. **Gobernanza SSoT y Reglas Inmutables (AGENTS.md §1.1)**: La estación base local no es un vecino de la malla ni un contacto; es el transceptor propio a través del cual el operador accede a la red.
2. **Protección Anti-Bucle (Loopback Guard)**: Todo paquete cuyo remitente coincida con la clave pública local (`local_pubkey`) debe ser identificado y filtrado para evitar re-despacho y publicaciones redundantes a MQTT o n8n.
3. **Claridad Operativa en UI/UX**: El operador debe distinguir de forma inequívoca el estado de la estación base host frente a los nodos remotos de campo.

## Decisión

1. **Aislamiento en Registro (`NodeRegistry`)**:
   - El transceptor local se almacena con la bandera `is_local = True`.
   - `NodeRegistry.list_client_contacts()` excluye incondicionalmente el nodo local.
2. **Guarda de Origen Propio (Loopback Guard)**:
   - En `rx_router.py` y `tx_controller.py`, cualquier intento de despachar mensajes directos dirigidos a la clave pública local es rechazado inmediatamente con error `HTTP 400 Bad Request` ("Bucle local prohibido: no se permite enviar mensajes hacia la propia estación base").
   - Las balizas emitidas por el propio nodo local son marcadas como `is_local_telem = True` y actualizan exclusivamente las variables de diagnóstico del host, sin propagarse a colas de retransmisión RF.
3. **Saneamiento Visual en la WebUI**:
   - En `nodes.js` e `index.html`, la tarjeta del nodo local omite los chips de batería LiPo y métricas RF engañosas, mostrando en su lugar el distintivo canónico: `🖥️ Estación Base Host USB | ⚡ 5V USB`.
   - En la vista de ajustes, la sección de telemetría local expone exclusivamente el estado de "Alimentación Host (USB 5V)".

## Consecuencias

- **Positivas**:
  - Imposibilidad de bucles locales o tormentas de eco en el bus serie o en MQTT.
  - La libreta de contactos solo refleja pares remotos legítimos.
  - Interfaz de usuario veraz y coherente con la realidad física del hardware USB.
- **Negativas / Compensaciones**:
  - El usuario no puede utilizar el chat para probar transmisiones "hacia sí mismo" (debe usar un segundo nodo físico o el simulador de radio).
