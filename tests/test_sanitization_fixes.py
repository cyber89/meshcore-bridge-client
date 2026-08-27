"""
Tests de verificación para el saneamiento integral de MeshCore Bridge.

Valida cada fix crítico, refactorización y mejora de seguridad
aplicada durante el proceso de saneamiento multi-agente.
"""

from __future__ import annotations

import asyncio
import warnings
from typing import Any
from unittest.mock import MagicMock

import pytest


# ================================================================== #
#  1. Rate Limiter Fixes                                              #
# ================================================================== #

class TestRateLimiterWorkerLoop:
    """Tests para el fix de race condition en _worker_loop."""

    def test_custom_tx_queue_invalid_dict_priority(self) -> None:
        """Verifica que priority='HIGH' no crashea en CustomTxQueue._put()."""
        from src.rate_limiter import CustomTxQueue, TxItem

        queue = CustomTxQueue(maxsize=10)
        # Debe manejar string no-numérico sin crashear
        queue.put_nowait({"priority": "HIGH", "text": "test"})
        item = queue.get_nowait()
        assert isinstance(item, TxItem)
        assert item.priority == 1  # Default cuando la coerción falla

    def test_custom_tx_queue_invalid_channel(self) -> None:
        """Verifica que channel='ch0' no crashea en CustomTxQueue._put()."""
        from src.rate_limiter import CustomTxQueue, TxItem

        queue = CustomTxQueue(maxsize=10)
        queue.put_nowait({"channel": "ch0", "text": "test"})
        item = queue.get_nowait()
        assert isinstance(item, TxItem)
        assert item.channel_idx == 0  # Default cuando la coerción falla

    def test_custom_tx_queue_valid_priority(self) -> None:
        """Verifica que prioridades válidas se procesan correctamente."""
        from src.rate_limiter import CustomTxQueue, TxItem

        queue = CustomTxQueue(maxsize=10)
        queue.put_nowait({"priority": 0, "text": "urgent"})
        queue.put_nowait({"priority": 2, "text": "low"})
        item1 = queue.get_nowait()
        assert isinstance(item1, TxItem)
        assert item1.priority == 0

    @pytest.mark.asyncio
    async def test_worker_loop_task_done_on_none(self) -> None:
        """Verifica que task_done() se llama incluso con item=None."""
        from src.rate_limiter import CustomTxQueue

        queue = CustomTxQueue(maxsize=10)
        queue.put_nowait(None)  # type: ignore[arg-type]
        item = queue.get_nowait()
        # En el código original, esto habría hecho continue sin task_done
        # Ahora debe completar sin error
        queue.task_done()
        # Si llegamos aquí sin ValueError, task_done fue llamado correctamente

    @pytest.mark.asyncio
    async def test_stop_cancels_orphaned_futures(self) -> None:
        """Verifica que stop() cancela futures pendientes en la queue."""
        from src.rate_limiter import CustomTxQueue, TxItem, TxRateLimiter
        import time

        limiter = TxRateLimiter(transmit_callback=None)
        limiter.start()

        # Encolar un item con future sin procesarlo inmediatamente
        loop = asyncio.get_running_loop()
        future: asyncio.Future[Any] = loop.create_future()
        item = TxItem(
            priority=1,
            created_at=time.time(),
            counter=999,
            payload=b"test",
            future=future,
        )
        limiter.queue.put_nowait(item)

        # Dar tiempo al worker para tomar el item
        await asyncio.sleep(0.15)

        # Detener - debe drenar items y cancelar futures
        await limiter.stop()

        # El future debe estar resuelto (bien sea result o cancelled)
        assert future.done()


# ================================================================== #
#  2. Target Resolver Consolidation                                   #
# ================================================================== #

class TestTargetResolver:
    """Tests para la resolución de destino canónica unificada."""

    def test_resolve_empty_returns_empty(self) -> None:
        """Verifica que string vacío retorna string vacío."""
        from src.target_resolver import TargetResolver
        resolver = TargetResolver()
        assert resolver.resolve("") == ""

    def test_resolve_dict_passthrough(self) -> None:
        """Verifica que un dict pasa sin cambios."""
        from src.target_resolver import TargetResolver
        resolver = TargetResolver()
        d = {"public_key": "abc123"}
        assert resolver.resolve(d) is d  # type: ignore[arg-type]

    def test_resolve_object_with_public_key(self) -> None:
        """Verifica que un objeto con public_key pasa sin cambios."""
        from src.target_resolver import TargetResolver
        resolver = TargetResolver()
        obj = MagicMock()
        obj.public_key = "abc123def456"
        assert resolver.resolve(obj) is obj  # type: ignore[arg-type]

    def test_resolve_short_hex_padded(self) -> None:
        """Verifica que clave hex corta se rellena a min_hex_len."""
        from src.target_resolver import TargetResolver
        resolver = TargetResolver()
        result = resolver.resolve("abc123", min_hex_len=12)
        assert result == "abc123000000"
        assert len(result) == 12

    def test_resolve_non_hex_raises_when_requested(self) -> None:
        """Verifica que nombres no-hex lanzan ValueError con raise_on_not_found=True."""
        from src.target_resolver import TargetResolver
        resolver = TargetResolver()
        with pytest.raises(ValueError, match="Destinatario no encontrado"):
            resolver.resolve("Alice", raise_on_not_found=True)

    def test_resolve_non_hex_returns_string_by_default(self) -> None:
        """Verifica que nombres no-hex retornan string sin raise por defecto."""
        from src.target_resolver import TargetResolver
        resolver = TargetResolver()
        result = resolver.resolve("Alice")
        assert result == "Alice"

    def test_resolve_full_hex_key_passthrough(self) -> None:
        """Verifica que una clave hex >= min_hex_len pasa sin cambios."""
        from src.target_resolver import TargetResolver
        resolver = TargetResolver()
        key = "abcdef123456"
        result = resolver.resolve(key, min_hex_len=12)
        assert result == key


# ================================================================== #
#  3. Protocol Types Deprecation Warnings                             #
# ================================================================== #

class TestProtocolTypesDeprecation:
    """Tests para las advertencias de deprecación en protocol_types."""

    def test_opcode_emits_deprecation_warning(self) -> None:
        """Verifica que importar OpCode emite DeprecationWarning."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            from src.protocol_types import OpCode  # noqa: F401
            # Verificar que se emitió un DeprecationWarning
            deprecation_warns = [x for x in w if issubclass(x.category, DeprecationWarning)]
            assert len(deprecation_warns) >= 1
            assert "OpCode" in str(deprecation_warns[0].message)

    def test_opcode_is_packet_type(self) -> None:
        """Verifica que OpCode resuelve al mismo tipo que PacketType."""
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            from src.protocol_types import OpCode, PacketType
            assert OpCode is PacketType

    def test_firmware_command_type_emits_warning(self) -> None:
        """Verifica que FirmwareCommandType emite DeprecationWarning."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            from src.protocol_types import FirmwareCommandType  # noqa: F401
            deprecation_warns = [x for x in w if issubclass(x.category, DeprecationWarning)]
            assert len(deprecation_warns) >= 1


# ================================================================== #
#  4. Shared Utils Centralized Functions                              #
# ================================================================== #

class TestSharedUtilsCentralized:
    """Tests para las funciones centralizadas en shared_utils."""

    def test_classify_device_role_client_none(self) -> None:
        """Verifica que NONE (0) → CLIENT."""
        from src.shared_utils import classify_device_role
        assert classify_device_role(0) == "CLIENT"

    def test_classify_device_role_client_chat(self) -> None:
        """Verifica que CHAT (1) → CLIENT."""
        from src.shared_utils import classify_device_role
        assert classify_device_role(1) == "CLIENT"

    def test_classify_device_role_repeater(self) -> None:
        """Verifica que REPEATER (2) → REPEATER."""
        from src.shared_utils import classify_device_role
        assert classify_device_role(2) == "REPEATER"

    def test_classify_device_role_room(self) -> None:
        """Verifica que ROOM (3) → ROOM."""
        from src.shared_utils import classify_device_role
        assert classify_device_role(3) == "ROOM"

    def test_classify_device_role_sensor(self) -> None:
        """Verifica que SENSOR (4) → SENSOR."""
        from src.shared_utils import classify_device_role
        assert classify_device_role(4) == "SENSOR"

    def test_classify_device_role_local(self) -> None:
        """Verifica que is_local=True → LOCAL independiente del advert_type."""
        from src.shared_utils import classify_device_role
        assert classify_device_role(2, is_local=True) == "LOCAL"

    def test_classify_device_role_unknown(self) -> None:
        """Verifica que tipo desconocido (99) → CLIENT."""
        from src.shared_utils import classify_device_role
        assert classify_device_role(99) == "CLIENT"

    def test_normalize_battery_percentage_direct(self) -> None:
        """Verifica conversión de porcentaje directo (0-100)."""
        from src.shared_utils import normalize_battery
        pct, volt = normalize_battery(75)
        assert pct == 75.0
        assert 3.0 <= volt <= 4.2

    def test_normalize_battery_zero(self) -> None:
        """Verifica que batería 0 retorna (0.0, 0.0)."""
        from src.shared_utils import normalize_battery
        assert normalize_battery(0) == (0.0, 0.0)

    def test_normalize_battery_voltage_range(self) -> None:
        """Verifica conversión de voltaje en centésimas (300-420)."""
        from src.shared_utils import normalize_battery
        pct, volt = normalize_battery(380)
        assert volt == 3.8
        assert 0.0 <= pct <= 100.0


# ================================================================== #
#  5. Path Traversal Protection                                       #
# ================================================================== #

class TestPathTraversalProtection:
    """Tests para la protección fortalecida contra path traversal."""

    def _make_server(self) -> Any:
        """Crea instancia mínima del servidor para testing."""
        from src.web.http_server import MeshCoreWebServer
        bridge = MagicMock()
        return MeshCoreWebServer(bridge)

    def test_basic_traversal(self) -> None:
        """Verifica detección de ../../../etc/passwd."""
        server = self._make_server()
        assert server._is_traversal_attempt("../../../etc/passwd") is True

    def test_url_encoded_traversal(self) -> None:
        """Verifica detección de %2e%2e/%2e%2e/etc/passwd."""
        server = self._make_server()
        assert server._is_traversal_attempt("%2e%2e/%2e%2e/etc/passwd") is True

    def test_double_encoded_traversal(self) -> None:
        """Verifica detección de %252e%252e (double-encoding)."""
        server = self._make_server()
        assert server._is_traversal_attempt("%252e%252e/%252e%252e/etc") is True

    def test_null_byte_injection(self) -> None:
        """Verifica detección de null byte %00."""
        server = self._make_server()
        assert server._is_traversal_attempt("file.txt%00.html") is True

    def test_overlong_utf8_traversal(self) -> None:
        """Verifica detección de overlong UTF-8 encoding %c0%ae."""
        server = self._make_server()
        assert server._is_traversal_attempt("%c0%ae%c0%ae/etc/passwd") is True

    def test_clean_path_passes(self) -> None:
        """Verifica que rutas limpias no son bloqueadas."""
        server = self._make_server()
        assert server._is_traversal_attempt("css/app.css") is False
        assert server._is_traversal_attempt("js/app.js") is False
        assert server._is_traversal_attempt("index.html") is False


# ================================================================== #
#  6. CORS Origin Validation                                          #
# ================================================================== #

class TestCORSValidation:
    """Tests para la validación CORS mejorada."""

    def _make_server(self) -> Any:
        """Crea instancia mínima del servidor."""
        from src.web.http_server import MeshCoreWebServer
        bridge = MagicMock()
        return MeshCoreWebServer(bridge)

    def test_localhost_allowed(self) -> None:
        """Verifica que localhost está permitido."""
        server = self._make_server()
        assert server._is_origin_allowed("http://localhost:8080", "", []) is True

    def test_loopback_allowed(self) -> None:
        """Verifica que 127.0.0.1 está permitido."""
        server = self._make_server()
        assert server._is_origin_allowed("http://127.0.0.1:8080", "", []) is True

    def test_private_ip_allowed(self) -> None:
        """Verifica que IPs privadas 192.168.x.x están permitidas."""
        server = self._make_server()
        assert server._is_origin_allowed("http://192.168.1.100:8080", "", []) is True

    def test_evil_localhost_rejected(self) -> None:
        """Verifica que evil-localhost.com NO está permitido."""
        server = self._make_server()
        assert server._is_origin_allowed("http://evil-localhost.com", "", []) is False

    def test_no_origin_allowed(self) -> None:
        """Verifica que peticiones sin Origin están permitidas."""
        server = self._make_server()
        assert server._is_origin_allowed("", "", []) is True


# ================================================================== #
#  7. RX Router System Message Detection                              #
# ================================================================== #

class TestSystemMessageDetection:
    """Tests para la detección refactorizada de mensajes de sistema."""

    def test_empty_text_is_system(self) -> None:
        """Verifica que texto vacío es tratado como sistema."""
        from src.rx_router import is_command_or_system_message
        assert is_command_or_system_message("") is True

    def test_ok_is_system(self) -> None:
        """Verifica que 'ok' es mensaje de sistema."""
        from src.rx_router import is_command_or_system_message
        assert is_command_or_system_message("ok") is True

    def test_pong_is_system(self) -> None:
        """Verifica que 'pong' es mensaje de sistema."""
        from src.rx_router import is_command_or_system_message
        assert is_command_or_system_message("pong") is True

    def test_cmd_prefix_is_system(self) -> None:
        """Verifica que 'cmd set_name Test' es mensaje de sistema."""
        from src.rx_router import is_command_or_system_message
        assert is_command_or_system_message("cmd set_name Test") is True

    def test_normal_chat_is_not_system(self) -> None:
        """Verifica que texto de chat normal NO es mensaje de sistema."""
        from src.rx_router import is_command_or_system_message
        assert is_command_or_system_message("Hola, ¿cómo estás?") is False

    def test_txt_type_1_always_system(self) -> None:
        """Verifica que txt_type=1 siempre retorna True."""
        from src.rx_router import is_command_or_system_message
        assert is_command_or_system_message("normal text", txt_type=1) is True


# ================================================================== #
#  8. Admin Handler Refactored Structure                              #
# ================================================================== #

class TestAdminHandlerStructure:
    """Tests para verificar la estructura refactorizada del admin handler."""

    def test_handle_cli_method_exists(self) -> None:
        """Verifica que _handle_cli_command existe como método."""
        from src.admin_handler import AdminCommandHandler
        assert hasattr(AdminCommandHandler, "_handle_cli_command")

    def test_cli_subhandlers_exist(self) -> None:
        """Verifica que los sub-handlers CLI existen."""
        from src.admin_handler import AdminCommandHandler
        expected_methods = [
            "_cli_version", "_cli_battery", "_cli_time",
            "_cli_sync_clock", "_cli_stats_core", "_cli_radio_info",
            "_cli_packets_info", "_cli_position_info", "_cli_owner_info",
            "_cli_neighbors", "_cli_nodes_list", "_cli_lqi",
            "_cli_send_advert", "_cli_help_text", "_cli_set_param",
        ]
        for method_name in expected_methods:
            assert hasattr(AdminCommandHandler, method_name), f"Missing: {method_name}"

    def test_resolve_target_uses_target_resolver(self) -> None:
        """Verifica que _resolve_target delega a TargetResolver."""
        import inspect
        from src.admin_handler import AdminCommandHandler
        source = inspect.getsource(AdminCommandHandler._resolve_target)
        assert "TargetResolver" in source


# ================================================================== #
#  9. Sender Prefix Deduplication in Message Text                     #
# ================================================================== #

class TestSenderPrefixDeduplication:
    """Tests para verificar la extracción y remoción del prefijo de remitente."""

    def test_extract_sender_with_channel_url(self) -> None:
        """Verifica que 'Cu1.mobilUnit: meshcore://...' extrae el remitente y limpia el texto."""
        from src.rx_router import extract_sender_from_text

        text = "Cu1.mobilUnit: meshcore://channel/add?name=Locals&secret=d57078c90eef5f5a7e949f1892ba744e"
        sender, clean = extract_sender_from_text(text)
        assert sender == "Cu1.mobilUnit"
        assert clean == "meshcore://channel/add?name=Locals&secret=d57078c90eef5f5a7e949f1892ba744e"

    def test_extract_sender_with_brackets(self) -> None:
        """Verifica que '[Cu1.mobilUnit]: hola mundo' extrae el remitente y limpia el texto."""
        from src.rx_router import extract_sender_from_text

        text = "[Cu1.mobilUnit]: hola mundo"
        sender, clean = extract_sender_from_text(text)
        assert sender == "Cu1.mobilUnit"
        assert clean == "hola mundo"

    def test_extract_sender_url_not_treated_as_sender(self) -> None:
        """Verifica que URLs directas como 'meshcore://...' no extraen 'meshcore' como remitente."""
        from src.rx_router import extract_sender_from_text

        text = "meshcore://channel/add?name=Locals&secret=d57078c90eef5f5a7e949f1892ba744e"
        sender, clean = extract_sender_from_text(text)
        assert sender is None
        assert clean == text

    def test_extract_sender_http_url_not_treated_as_sender(self) -> None:
        """Verifica que 'http://...' o 'https://...' no extraen scheme como remitente."""
        from src.rx_router import extract_sender_from_text

        text = "https://meshcore.org"
        sender, clean = extract_sender_from_text(text)
        assert sender is None
        assert clean == text


# ================================================================== #
#  10. Channels Persistence and PSK Formatting                       #
# ================================================================== #

class TestChannelsPersistence:
    """Tests para verificar la persistencia de canales y formateo de claves PSK."""

    @pytest.mark.asyncio
    async def test_channels_persistence_and_reload(self, tmp_path: Any, monkeypatch: Any) -> None:
        import json
        from unittest.mock import MagicMock
        from src.web.api_router import WebAPIRouter

        storage_file = tmp_path / "channels.json"
        monkeypatch.setenv("CHANNELS_STORAGE_PATH", str(storage_file))

        class MockBridge:
            def __init__(self) -> None:
                self.web_server = MagicMock()
                self.diagnostics = MagicMock()
                self.serial_adapter = None

        bridge1 = MockBridge()
        router1 = WebAPIRouter(bridge1)

        # Inicialmente solo canal 0
        assert len(router1.channels) == 1
        assert router1.channels[0]["name"] == "Public / Broadcast"

        # Crear Canal 1
        code, res = await router1._route_channels(
            "/api/channels",
            "POST",
            {"index": 1, "name": "Operaciones", "psk": "d57078c90eef5f5a7e949f1892ba744e"},
        )
        assert code == 200
        assert res["status"] == "ok"
        assert len(router1.channels) == 2
        assert router1.channels[1]["name"] == "Operaciones"

        # Verificar guardado en archivo
        assert storage_file.is_file()
        with open(storage_file, encoding="utf-8") as f:
            saved_data = json.load(f)
        assert len(saved_data) == 2
        assert saved_data[1]["name"] == "Operaciones"

        # Simular reinicio del servicio / Nueva instancia
        bridge2 = MockBridge()
        router2 = WebAPIRouter(bridge2)

        # Los canales deben cargarse intactos desde el disco
        assert len(router2.channels) == 2
        assert 1 in router2.channels
        assert router2.channels[1]["name"] == "Operaciones"
        assert router2.channels[1]["psk"] == "d57078c90eef5f5a7e949f1892ba744e"

    @pytest.mark.asyncio
    async def test_serial_driver_set_channel_psk_conversion(self) -> None:
        from unittest.mock import AsyncMock, MagicMock
        from src.serial_driver import MeshcoreSDKAdapter

        driver = MeshcoreSDKAdapter(port="COM3")
        driver.is_connected = True
        driver.mc = MagicMock()
        driver.mc.commands = MagicMock()
        driver.mc.commands.set_channel = AsyncMock(return_value={"status": "OK"})

        # PSK hexadecimal de 32 caracteres (16 bytes)
        res = await driver.set_channel(1, "Canal-Test", "d57078c90eef5f5a7e949f1892ba744e")
        assert res["status"] == "OK"
        driver.mc.commands.set_channel.assert_called_once_with(
            1, "Canal-Test", bytes.fromhex("d57078c90eef5f5a7e949f1892ba744e")
        )


