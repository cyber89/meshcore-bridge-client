---
name: security-code-auditor
description: Auditar entradas, secretos, permisos y límites de MeshCore Bridge con evidencia de código y regresiones aisladas; distinguir heurísticas de pruebas de seguridad.
---

# Seguridad del bridge

Leer [AGENTS.md](../../../AGENTS.md) y los límites reales en
[http_server.py](../../../src/web/http_server.py), [config.py](../../../config.py)
y [tcp_companion_server.py](../../../src/tcp_companion_server.py).
No copiar límites de ejemplos: extraer configuración y constantes vigentes.

- Validar esquemas, rangos, tipos y longitudes antes de persistir o transmitir.
- Verificar aislamiento de repetidores y nodo local en contactos/chat y prohibición
  de loopback en todos los puntos de ingreso REST/MQTT/SDK.
- No publicar PSK, channel_secret, tokens o contraseñas en telemetría, logs o MQTT.
- Usar DOM textContent o escapeHtml en interpolaciones HTML; revisar contextos de URL
  y atributos por separado. No escapar dos veces ni considerar escapeHtml un sanitizador universal.
- Revisar resolución y pertenencia de rutas estáticas, límites HTTP/WebSocket/MQTT,
  colas, conexiones Companion y comparación constante de tokens apropiados.
- CRC detecta corrupción; no autentica ni cifra. El canal Public usa una clave conocida
  y no proporciona confidencialidad frente a otros participantes.

```bash
python .agents/skills/security-code-auditor/scripts/run_security_audit.py
python -m bandit -r src -ll -ii
```

El helper combina Bandit y reglas heurísticas. Reportar qué ejecutó y sus limitaciones;
no llamarlo auditoría DAST completa ni garantizar cero vulnerabilidades. Peticiones
dinámicas y suites requieren autorización y servicios virtuales propios.
