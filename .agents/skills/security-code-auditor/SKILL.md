---
name: security-code-auditor
description: >-
  Herramienta y orquestador de auditoría de seguridad informática y análisis estático SAST/DAST
  para MeshCore Bridge. Evalúa vulnerabilidades OWASP Top 10, validación de esquemas JSON,
  ataques de Directory Traversal, sanitización XSS, seguridad de WebSockets, límites contra DoS
  y validación de criptografía (AES/PSK/CRC).
---

# Security Code Auditor Skill

Esta skill dota al **Security & Vulnerability Auditor Agent** de capacidades de análisis estático y dinámico de seguridad sobre la base de código de MeshCore Bridge.

## Objetivos de la Auditoría y OWASP API Security Top 10
1. **Broken Object Level Authorization (BOLA) & Guardarraíles**:
   - Verificar que ningún identificador de nodo permita mutar o enviar mensajes indebidos a transceptores protegidos (`is_local_key`, exclusión de repetidores en chat).
2. **Validación de Esquemas e Inyección**:
   - Validar tipos, longitudes y formatos estrictos (hexadecimal de 64 caracteres para claves públicas, rangos numéricos acotados en radio y frecuencias).
3. **Unrestricted Resource Consumption & DoS**:
   - Límites en payloads (`MAX_BODY_SIZE = 64KB`), buffers de historial acotados con `deque(maxlen=1000)` y colas `asyncio.Queue(maxsize=...)`.
4. **Directory Traversal**:
   - Restricción estricta en `src/web/http_server.py` hacia `src/web/static/` mediante resolución canónica (`.resolve()`) y verificación de pertenencia (`is_relative_to()`).
5. **Cross-Site Scripting (XSS)**:
   - Sanitización obligatoria con `escapeHtml` en todas las variables dinámicas antes de ser inyectadas en plantillas o elementos DOM.
6. **Criptografía y Comparación en Tiempo Constante**:
   - Para tokens administrativos, contraseñas de repetidores y verificación de hashes, usar `hmac.compare_digest()` para prevenir ataques de temporización (timing attacks).
7. **Cabeceras de Seguridad HTTP**:
   - `Content-Security-Policy`, `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: strict-origin-when-cross-origin`.

## Ejecución del Auditor
```bash
python .agents/skills/security-code-auditor/scripts/run_security_audit.py
```

