"""Opt-in MQTT TLS validates identity; never connects to an operational broker."""
from __future__ import annotations

import asyncio
import ssl
from contextlib import suppress
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from src.mqtt_client import AsyncBridgeMQTTClient, MQTTConfig


def test_default_mqtt_transport_is_preserved() -> None:
    with patch("src.mqtt_client.mqtt.Client") as factory:
        AsyncBridgeMQTTClient(MQTTConfig())
    factory.return_value.tls_set_context.assert_not_called()


def test_tls_context_verifies_certificate_and_hostname() -> None:
    with patch("src.mqtt_client.mqtt.Client") as factory:
        AsyncBridgeMQTTClient(MQTTConfig(tls_enabled=True))
    context = factory.return_value.tls_set_context.call_args.args[0]
    assert isinstance(context, ssl.SSLContext)
    assert context.verify_mode == ssl.CERT_REQUIRED and context.check_hostname
    assert context.keylog_filename is None
    factory.return_value.connect_async.assert_not_called()


def test_custom_ca_and_mutual_auth_are_loaded_before_connect() -> None:
    context = MagicMock()
    with patch("src.mqtt_client.ssl.create_default_context", return_value=context) as create, patch("src.mqtt_client.mqtt.Client") as factory:
        AsyncBridgeMQTTClient(MQTTConfig(tls_enabled=True, tls_ca_file="ca.pem", tls_cert_file="cert.pem", tls_key_file="key.pem"))
    create.assert_called_once_with(cafile="ca.pem")
    context.load_cert_chain.assert_called_once_with(certfile="cert.pem", keyfile="key.pem")
    factory.return_value.tls_set_context.assert_called_once_with(context)
    factory.return_value.connect_async.assert_not_called()


@pytest.mark.parametrize("settings", [
    {"tls_enabled": True, "tls_cert_file": "cert.pem"},
    {"tls_enabled": True, "tls_key_file": "key.pem"},
    {"tls_enabled": False, "tls_ca_file": "ca.pem"},
    {"tls_enabled": "false"},
])
def test_incomplete_or_ambiguous_tls_configuration_fails_closed(settings: dict) -> None:
    with patch("src.mqtt_client.mqtt.Client") as factory, pytest.raises(ValueError):
        AsyncBridgeMQTTClient(MQTTConfig(**settings))
    factory.return_value.connect_async.assert_not_called()


def test_unreadable_ca_has_no_plaintext_fallback(tmp_path) -> None:
    with patch("src.mqtt_client.mqtt.Client") as factory, pytest.raises(FileNotFoundError):
        AsyncBridgeMQTTClient(MQTTConfig(tls_enabled=True, tls_ca_file=str(tmp_path / "missing.pem")))
    factory.return_value.connect_async.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("trust,hostname,valid", [(True, "localhost", True), (False, "localhost", False), (True, "127.0.0.1", False)])
async def test_real_paho_tls_on_ephemeral_loopback(tmp_path, trust: bool, hostname: str, valid: bool) -> None:
    # Certificate generation is an optional QA dependency, never a runtime one.
    pytest.importorskip("cryptography")
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
    now = datetime.now(timezone.utc)
    certificate = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
        .public_key(key.public_key()).serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1)).not_valid_after(now + timedelta(days=1))
        .add_extension(x509.SubjectAlternativeName([x509.DNSName("localhost")]), critical=False)
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(key, hashes.SHA256()))
    cert_path, key_path = tmp_path / "cert.pem", tmp_path / "key.pem"
    cert_path.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    server_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server_context.load_cert_chain(cert_path, key_path)
    tasks: set[asyncio.Task] = set()
    writers: set[asyncio.StreamWriter] = set()

    async def connection(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        task = asyncio.current_task()
        if task:
            tasks.add(task)
        writers.add(writer)
        try:
            assert await reader.readexactly(1) == b"\x10"
            remaining, multiplier = 0, 1
            for _ in range(4):
                byte = (await reader.readexactly(1))[0]
                remaining += (byte & 127) * multiplier
                if byte < 128:
                    break
                multiplier *= 128
            else:
                raise AssertionError("Invalid MQTT remaining length")
            await reader.readexactly(remaining)
            writer.write(b"\x20\x02\x00\x00")
            await writer.drain()
            await reader.read()
        finally:
            writer.close()
            with suppress(ssl.SSLError, ConnectionError):
                await writer.wait_closed()
            writers.discard(writer)
            if task:
                tasks.discard(task)

    server = await asyncio.start_server(connection, "127.0.0.1", 0, ssl=server_context)
    port = server.sockets[0].getsockname()[1]
    client = AsyncBridgeMQTTClient(MQTTConfig(broker=hostname, port=port, tls_enabled=True,
                                             tls_ca_file=str(cert_path) if trust else None))
    try:
        if valid:
            assert await asyncio.to_thread(client.client.connect, hostname, port, 60) == 0
            client.client.loop_start()
            for _ in range(200):
                if client.is_connected:
                    break
                await asyncio.sleep(0.01)
            assert client.is_connected
        else:
            with pytest.raises(ssl.SSLCertVerificationError):
                await asyncio.to_thread(client.client.connect, hostname, port, 60)
            assert not client.is_connected
    finally:
        await asyncio.to_thread(client.stop)
        server.close()
        await server.wait_closed()
        for writer in tuple(writers):
            writer.close()
        if tasks:
            await asyncio.gather(*tuple(tasks), return_exceptions=True)
