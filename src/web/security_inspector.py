"""
MeshCore Bridge - Security Traffic Inspector & Ingress Connection Logger.
Módulo de seguridad e inspección de tráfico en tiempo real que registra todas las
conexiones IP a la interfaz Web, API REST, WebSocket y servidor TCP Companion,
detectando y alertando sobre patrones de tráfico anómalo o sospechoso.
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any
from urllib.parse import unquote


class SecurityTrafficInspector:
    """
    Inspector de seguridad perimetral para MeshCore Bridge.
    Registra accesos por IP y detecta vectores de ataque conocidos, sondeos de vulnerabilidad,
    intentos de Directory Traversal e inyecciones de código.
    """

    # Herramientas y firmas de escáneres automáticos de vulnerabilidad
    SCANNER_USER_AGENTS = (
        "sqlmap",
        "nikto",
        "nmap",
        "gobuster",
        "dirbuster",
        "nuclei",
        "masscan",
        "wpscan",
        "acunetix",
        "nessus",
        "zgrab",
        "censys",
        "shodan",
        "whatweb",
        "openvas",
        "arachni",
    )

    # Rutas sensibles buscadas comúnmente por bots y atacantes
    SUSPICIOUS_PATH_PATTERNS = (
        r"/\.env",
        r"/\.git",
        r"/wp-login\.php",
        r"/wp-admin",
        r"/phpmyadmin",
        r"/actuator",
        r"/swagger-ui",
        r"/api-docs",
        r"/shell",
        r"/cgi-bin/",
        r"/xmlrpc\.php",
        r"/\.well-known/security\.txt",
        r"/admin\.php",
        r"/manager/html",
        r"/\.aws/",
        r"/\.ssh/",
        r"/web\.config",
        r"/id_rsa",
        r"/etc/passwd",
        r"/etc/shadow",
        r"/windows/win\.ini",
        r"/system32/",
        r"/config\.json",
        r"/\.ds_store",
    )

    # Patrones de inyección de comandos o scripts
    INJECTION_PATTERNS = (
        r"<script[\s>]",
        r"javascript:",
        r"onerror\s*=",
        r"onload\s*=",
        r"cmd\.exe",
        r"/bin/sh",
        r"/bin/bash",
        r"powershell",
        r";\s*cat\s+",
        r"\|\s*curl\s+",
        r"\|\s*wget\s+",
        r"UNION\s+SELECT",
        r"DROP\s+TABLE",
        r"eval\(",
        r"\$\{jndi:",
    )

    _path_regex = re.compile("|".join(SUSPICIOUS_PATH_PATTERNS), re.IGNORECASE)
    _injection_regex = re.compile("|".join(INJECTION_PATTERNS), re.IGNORECASE)

    @classmethod
    def extract_client_ip(
        cls,
        writer: asyncio.StreamWriter,
        headers: dict[str, str] | None = None,
    ) -> str:
        """Extrae y normaliza la dirección IP del cliente desde el socket o encabezados proxy."""
        if headers:
            # Si hay proxy inverso o CDN configurado
            forwarded = headers.get("x-forwarded-for", "")
            if forwarded:
                client_ip = forwarded.split(",")[0].strip()
                if client_ip:
                    return client_ip
            real_ip = headers.get("x-real-ip", "").strip()
            if real_ip:
                return real_ip

        peer = writer.get_extra_info("peername")
        if peer and isinstance(peer, (tuple, list)) and len(peer) >= 1:
            raw_ip = str(peer[0])
            # Limpiar notación IPv4 mapeada en IPv6 si aplica
            if raw_ip.startswith("::ffff:"):
                return raw_ip[7:]
            return raw_ip
        return "127.0.0.1"

    @classmethod
    def is_traversal_attempt(cls, raw_path: str) -> bool:
        """Detecta intentos de Directory Traversal en la ruta solicitada."""
        normalized = raw_path.replace("\\", "/")
        low = normalized.lower()
        try:
            decoded = unquote(unquote(low))
        except Exception:
            decoded = low

        parts = [p.strip() for p in normalized.split("/") if p.strip()]
        decoded_parts = [p.strip() for p in decoded.split("/") if p.strip()]

        return (
            ".." in parts
            or ".." in decoded_parts
            or "%2e" in low
            or "%2f" in low
            or "%00" in low
            or "%c0%ae" in low
            or "..../" in normalized
            or "\x00" in raw_path
            or "/etc/passwd" in low
            or "win.ini" in low
        )

    @classmethod
    def inspect_http_request(
        cls,
        method: str,
        path: str,
        headers: dict[str, str],
        body_dict: dict[str, Any] | None = None,
        client_ip: str = "127.0.0.1",
    ) -> tuple[bool, str, str]:
        """
        Inspecciona una solicitud HTTP entrante en busca de comportamientos sospechosos o ataques.
        Retorna: (es_sospechoso, tipo_anomalia, detalle)
        """
        user_agent = headers.get("user-agent", "").lower()

        # 1. Detección de herramientas de escaneo y auditoría automática
        for scanner in cls.SCANNER_USER_AGENTS:
            if scanner in user_agent:
                return True, "SCANNER_AUTOMATIZADO", f"User-Agent identificado como escáner: '{scanner}'"

        # 2. Longitud anormal de URL o encabezados (intento de Buffer Overflow / DoS)
        if len(path) > 1024:
            return True, "LONGITUD_URL_EXCESIVA", f"Path excede 1024 caracteres ({len(path)} chars)"

        # 3. Detección de Directory Traversal
        if cls.is_traversal_attempt(path):
            return True, "DIRECTORY_TRAVERSAL", f"Intento de escape de directorio detectado en path: '{path}'"

        # 4. Detección de sondeos a rutas sensibles no existentes
        clean_path = path.split("?")[0]
        if cls._path_regex.search(clean_path):
            match = cls._path_regex.search(clean_path)
            matched_pattern = match.group(0) if match else clean_path
            return True, "SONDEO_RUTA_SENSIBLE", f"Petición a archivo o ruta restringida/trampa: '{matched_pattern}'"

        # 5. Detección de Inyección de Comandos / Scripts en la Query String o Path
        if cls._injection_regex.search(path):
            match = cls._injection_regex.search(path)
            matched_pattern = match.group(0) if match else "patron_inyeccion"
            return True, "INYECCION_COMANDO_O_SCRIPT", f"Patrón de inyección detectado en URI: '{matched_pattern}'"

        # 6. Inspección superficial del cuerpo JSON si existe
        if body_dict:
            raw_body_str = str(body_dict)
            if len(raw_body_str) < 4096 and cls._injection_regex.search(raw_body_str):
                match = cls._injection_regex.search(raw_body_str)
                matched_pattern = match.group(0) if match else "inyeccion_body"
                return True, "INYECCION_EN_PAYLOAD", f"Patrón malicioso en payload: '{matched_pattern}'"

        return False, "", ""

    @classmethod
    def log_http_access(
        cls,
        client_ip: str,
        method: str,
        path: str,
        status_code: int,
        duration_ms: float,
        user_agent: str = "",
    ) -> None:
        """Registra una conexión HTTP o consulta REST de forma limpia y estructurada."""
        is_api = path.startswith("/api/")
        tag = "[REST-API]" if is_api else "[HTTP-CLIENT]"
        clean_path = path.split("?")[0]
        ua_summary = user_agent[:40] + "..." if len(user_agent) > 40 else (user_agent or "N/D")

        if is_api:
            logging.info(
                f"⚡ {tag} IP: {client_ip} -> {method} {clean_path} | Código: {status_code} | {duration_ms:.1f}ms"
            )
        else:
            logging.info(
                f"🌐 {tag} IP: {client_ip} -> {method} {clean_path} | Código: {status_code} | {duration_ms:.1f}ms | UA: {ua_summary}"
            )

    @classmethod
    def log_suspicious_traffic(
        cls,
        client_ip: str,
        source_type: str,
        endpoint: str,
        anomaly_type: str,
        detail: str,
        user_agent: str = "",
    ) -> None:
        """Registra un evento de tráfico sospechoso con alta visibilidad en el sistema de logs."""
        ua_info = f" | UA: '{user_agent[:60]}'" if user_agent else ""
        logging.warning(
            f"🚨 [TRAFICO-SOSPECHOSO] [{source_type}] IP: {client_ip} | Tipo: {anomaly_type} | Endpoint: {endpoint} | Detalle: {detail}{ua_info}"
        )

    @classmethod
    def log_tcp_connection(
        cls,
        client_ip: str,
        port: int,
        event: str,
        active_count: int,
    ) -> None:
        """Registra eventos de conexión y desconexión en el servidor TCP Companion."""
        logging.info(
            f"📶 [TCP-COMPANION] IP: {client_ip}:{port} -> {event} (Clientes activos: {active_count})"
        )

    @classmethod
    def log_websocket_connection(
        cls,
        client_ip: str,
        event: str,
        active_count: int,
    ) -> None:
        """Registra eventos de conexión y desconexión en el canal WebSocket."""
        logging.info(
            f"🔌 [WEBSOCKET] IP: {client_ip} -> {event} (Clientes activos: {active_count})"
        )
