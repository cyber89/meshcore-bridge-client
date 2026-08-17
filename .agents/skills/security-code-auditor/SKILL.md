---
name: security-code-auditor
description: >-
  Herramienta y orquestador de auditoría de seguridad informática y análisis estático SAST/DAST
  para MeshCore Bridge. Evalúa vulnerabilidades OWASP Top 10, inyecciones SQL en SQLite,
  ataques de Directory Traversal, sanitización XSS, seguridad de WebSockets, límites contra DoS
  y validación de criptografía (AES/PSK/CRC).
---

# Security Code Auditor Skill

Esta skill dota al **Security & Vulnerability Auditor Agent** de capacidades de análisis estático y dinámico de seguridad sobre la base de código de MeshCore Bridge.

## Objetivos de la Auditoría
1. **Inyección SQL**: Verificar que todas las consultas a SQLite en `src/store_forward.py` utilicen consultas parametrizadas (`?`) sin concatenación directa de strings.
2. **Directory Traversal**: Verificar que el servidor estático `src/web/http_server.py` restrinja el acceso únicamente al directorio `src/web/static/` mediante resolución canónica (`.resolve()`).
3. **Cross-Site Scripting (XSS)**: Verificar que todos los datos recibidos por RF o APIs se escapen antes de ser insertados en el DOM (`escapeHtml`).
4. **Denegación de Servicio (DoS)**: Verificar límites de tamaño en cargas útiles JSON, protección contra floods de tramas y colas con tamaño acotado (`maxlen` en deques, `max_size` en SQLite).
5. **Cabeceras de Seguridad HTTP**: Verificar la presencia de `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY` y protección contra MIME-sniffing.
6. **Manejo Seguro de Criptografía**: Comprobar que no existan secretos hardcodeados en producción y que los identificadores de sesión o tokens usen generadores criptográficamente seguros.

## Ejecución del Auditor
```bash
python .agents/skills/security-code-auditor/scripts/run_security_audit.py
```
