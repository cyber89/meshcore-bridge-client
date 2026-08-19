---
name: gof-design-patterns-expert
description: >-
  Catálogo y directrices de implementación de patrones de diseño clásicos (GoF) y micro-patrones
  en Python moderno: Strategy, Factory Method, Adapter, Observer, Command, State Machine,
  Facade, Builder y Object Pool.
---

# GoF & Modern Design Patterns Skill

Esta skill proporciona una guía sistemática para seleccionar, implementar y refactorizar patrones de diseño orientados a objetos y funcionales en Python `>= 3.10`.

---

## 1. Patrones Creacionales

1. **Factory Method / Registry Pattern**:
   * **Propósito**: Crear instancias de adaptadores o serializadores sin acoplar el código cliente a clases concretas.
   * **Ejemplo**: `create_serial_adapter(config) -> BaseSerialAdapter` (instancia `MeshcoreSDKAdapter` o `VirtualMeshAdapter` según configuración).
2. **Builder Pattern**:
   * **Propósito**: Construcción paso a paso de tramas binarias complejas con encabezados opcionales, criptografía y padding.
3. **Singleton / Inyección de Dependencias**:
   * **Regla**: Evitar Singletons globales mutables; preferir inyección explícita de dependencias a través del constructor `__init__`.

---

## 2. Patrones Estructurales

1. **Adapter Pattern (Adaptador)**:
   * **Propósito**: Convertir la interfaz de una librería externa (ej. SDK de MeshCore, pyserial) en la interfaz esperada por el núcleo del bridge (`BaseSerialAdapter`).
2. **Facade Pattern (Fachada)**:
   * **Propósito**: Proveer una interfaz unificada y de alto nivel (`MeshCoreBridge`) que coordine subsistemas complejos (Serial, SQLite, MQTT, WebSockets, TCP Server).
3. **Proxy / Decorator Pattern**:
   * **Propósito**: Añadir logging, cálculo de métricas de latencia o reintentos automáticos de forma transparente sobre llamadas de red o comandos de radio.

---

## 3. Patrones Comportamentales

1. **Strategy Pattern (Estrategia)**:
   * **Propósito**: Intercambiar algoritmos de cálculo de CRC, compresión o delimitación en tiempo de ejecución.
2. **Observer / Pub-Sub Pattern**:
   * **Propósito**: Notificar a múltiples oyentes independientes cuando llega una nueva trama LoRa sin acoplar el receptor a los consumidores.
3. **Command Pattern (Comando)**:
   * **Propósito**: Encapsular una solicitud administrativa o de transmisión en un objeto con soporte para encolado, ejecución diferida y reintentos.
4. **State Machine (Máquina de Estados)**:
   * **Propósito**: Gestionar transiciones deterministas del ciclo de vida del transceptor: `DISCONNECTED -> CONNECTING -> BOOTSTRAPPING -> READY -> RECONNECTING -> STOPPED`.

---

## 4. Herramientas de Verificación

```bash
python .agents/skills/gof-design-patterns-expert/scripts/analyze_design_patterns.py
```
