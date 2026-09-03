"""
Prueba automatizada integral de registro de conexiones IP y detección de tráfico sospechoso
en Web, API REST, WebSocket y Servidor TCP Companion de MeshCore Bridge.
"""

import asyncio
import io
import logging
import sys
from pathlib import Path

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.bridge_core import MeshCoreBridge
from src.virtual_mesh_adapter import VirtualMeshAdapter


async def send_http_raw(host: str, port: int, request_text: str) -> tuple[int, str]:
    """Envía una petición HTTP de forma asíncrona no bloqueante."""
    r, w = await asyncio.open_connection(host, port)
    w.write(request_text.encode("utf-8"))
    await w.drain()
    response_data = await r.read(4096)
    w.close()
    await w.wait_closed()
    resp_str = response_data.decode("utf-8", errors="ignore")
    status_code = 0
    if resp_str.startswith("HTTP/"):
        parts = resp_str.split(" ")
        if len(parts) >= 2 and parts[1].isdigit():
            status_code = int(parts[1])
    return status_code, resp_str


async def test_ip_and_security_logging():
    log_capture = io.StringIO()
    handler = logging.StreamHandler(log_capture)
    logging.getLogger().addHandler(handler)
    logging.getLogger().setLevel(logging.INFO)

    web_port = 8098
    tcp_port = 5098

    bridge = MeshCoreBridge()
    if bridge.web_server:
        bridge.web_server.port = web_port
    if bridge.tcp_server:
        bridge.tcp_server.port = tcp_port

    v_adapter = VirtualMeshAdapter(event_callback=bridge.on_mesh_event)
    bridge.serial_adapter = v_adapter

    await v_adapter.connect()
    await bridge.web_server.start()
    await bridge.tcp_server.start()
    await asyncio.sleep(0.5)

    print(f"🚀 Servidores iniciados en Web:{web_port} y TCP:{tcp_port}")

    try:
        # 1. Probar acceso HTTP regular (Web UI)
        print("🌐 1. Probando acceso HTTP estático regular...")
        status, _ = await send_http_raw("127.0.0.1", web_port, "GET / HTTP/1.1\r\nHost: 127.0.0.1\r\nUser-Agent: Mozilla/5.0\r\nConnection: close\r\n\r\n")
        assert status == 200, f"Esperado 200, obtenido {status}"

        # 2. Probar acceso REST API
        print("⚡ 2. Probando consulta REST API (/api/nodes)...")
        status, _ = await send_http_raw("127.0.0.1", web_port, "GET /api/nodes HTTP/1.1\r\nHost: 127.0.0.1\r\nUser-Agent: MeshCore-Test\r\nConnection: close\r\n\r\n")
        assert status == 200, f"Esperado 200, obtenido {status}"

        # 3. Probar conexión TCP Companion regular
        print(f"📶 3. Probando conexión al servidor TCP Companion en puerto {tcp_port}...")
        reader, writer = await asyncio.open_connection("127.0.0.1", tcp_port)
        # Enviar trama Companion válida ('<' + len:0 + payload:[])
        writer.write(b"<\x00\x00")
        await writer.drain()
        await asyncio.sleep(0.2)
        writer.close()
        await writer.wait_closed()

        # 4. Probar detección de tráfico sospechoso: User-Agent escáner (sqlmap)
        print("🚨 4. Probando detección de escáner automatizado (User-Agent: sqlmap)...")
        status, _ = await send_http_raw("127.0.0.1", web_port, "GET /api/nodes HTTP/1.1\r\nHost: 127.0.0.1\r\nUser-Agent: sqlmap/1.7#stable\r\nConnection: close\r\n\r\n")
        assert status == 403, f"Esperado 403, obtenido {status}"
        print("  • Escáner bloqueado exitosamente con código 403 Forbidden")

        # 5. Probar detección de tráfico sospechoso: Sondeo de ruta sensible (/.env)
        print("🚨 5. Probando detección de sondeo de ruta sensible (/.env)...")
        status, _ = await send_http_raw("127.0.0.1", web_port, "GET /.env HTTP/1.1\r\nHost: 127.0.0.1\r\nUser-Agent: Mozilla/5.0\r\nConnection: close\r\n\r\n")
        assert status in (403, 404), f"Esperado 403 o 404, obtenido {status}"
        print(f"  • Sondeo a /.env detectado y bloqueado con código {status}")

        # 6. Probar detección de tráfico sospechoso: Directory Traversal (/../../etc/passwd)
        print("🚨 6. Probando detección de Directory Traversal (../../etc/passwd)...")
        status, _ = await send_http_raw("127.0.0.1", web_port, "GET /../../etc/passwd HTTP/1.1\r\nHost: 127.0.0.1\r\nUser-Agent: Mozilla/5.0\r\nConnection: close\r\n\r\n")
        assert status == 403, f"Esperado 403, obtenido {status}"
        print(f"  • Directory Traversal bloqueado con código {status}")

        # 7. Probar detección de trama TCP sobredimensionada en servidor Companion
        print("🚨 7. Probando detección de anomalía TCP (trama con longitud declarada > 512 bytes)...")
        tcp_r, tcp_w = await asyncio.open_connection("127.0.0.1", tcp_port)
        # Enviar '<' + longitud 9999 (0x0F, 0x27)
        tcp_w.write(b"<\x0F\x27" + b"X" * 100)
        await tcp_w.drain()
        await asyncio.sleep(0.3)
        tcp_w.close()
        await tcp_w.wait_closed()

        # Verificar logs capturados
        logs_output = log_capture.getvalue()
        print("\n=================== AUDITORÍA DE LOGS CAPTURADOS ===================")

        has_http_log = "[HTTP-CLIENT]" in logs_output
        has_api_log = "[REST-API]" in logs_output
        has_tcp_log = "[TCP-COMPANION]" in logs_output
        has_suspicious_log = "[TRAFICO-SOSPECHOSO]" in logs_output

        print(f"✓ Logs de Acceso HTTP [HTTP-CLIENT]:      {'PRESENTE' if has_http_log else 'FALTANTE'}")
        print(f"✓ Logs de Consultas API [REST-API]:        {'PRESENTE' if has_api_log else 'FALTANTE'}")
        print(f"✓ Logs de Servidor TCP [TCP-COMPANION]:    {'PRESENTE' if has_tcp_log else 'FALTANTE'}")
        print(f"✓ Alertas de Seguridad [TRAFICO-SOSPECHOSO]: {'PRESENTE' if has_suspicious_log else 'FALTANTE'}")

        assert has_http_log, "Falta registro de accesos HTTP con IP"
        assert has_api_log, "Falta registro de consultas REST con IP"
        assert has_tcp_log, "Falta registro de conexiones TCP Companion con IP"
        assert has_suspicious_log, "Falta registro de alertas de tráfico sospechoso"

        print("\n✅ ¡PASS! Todos los registros de conexiones IP y detección de anomalías funcionan al 100%.")
        return 0

    finally:
        await v_adapter.disconnect()
        await bridge.web_server.stop()
        await bridge.tcp_server.stop()
        logging.getLogger().removeHandler(handler)


if __name__ == "__main__":
    code = asyncio.run(test_ip_and_security_logging())
    sys.exit(code)
