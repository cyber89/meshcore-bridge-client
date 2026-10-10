"""Isolated MCP/Paramiko migration regressions; sockets are denied by default."""

import asyncio
import hashlib
import importlib.util
import io
import sys
import tarfile
from collections import namedtuple
from pathlib import Path
from unittest.mock import MagicMock

import pytest


@pytest.mark.parametrize("version,implementation", [
    ((3, 10, 0, "final", 0), "cpython"), ((3, 14, 8, "final", 0), "cpython"),
    ((3, 15, 0, "candidate", 1), "cpython"), ((3, 16, 0, "alpha", 1), "cpython"),
    ((3, 15, 0, "final", 0), "pypy"),
])
def test_unsupported_python_is_rejected_before_loading_mcp_or_paramiko(monkeypatch, version, implementation):
    import builtins

    runtime_version = namedtuple("RuntimeVersion", "major minor micro releaselevel serial")
    original_import = builtins.__import__
    external_imports = []

    def guarded_import(name, *args, **kwargs):
        if name == "paramiko" or name.startswith("mcp"):
            external_imports.append(name)
            raise AssertionError("Unsupported runtimes must stop before dependency imports")
        return original_import(name, *args, **kwargs)

    path = Path(__file__).resolve().parents[1] / "server.py"
    spec = importlib.util.spec_from_file_location("unsupported_runtime_ssh", path)
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setattr(sys, "version_info", runtime_version(*version))
    monkeypatch.setattr(sys.implementation, "name", implementation)
    monkeypatch.setattr(builtins, "__import__", guarded_import)
    with pytest.raises(RuntimeError, match="CPython 3.15.0 or newer stable"):
        spec.loader.exec_module(module)
    assert external_imports == []


@pytest.fixture
def maintenance(monkeypatch):
    import socket

    def deny_connection(*args, **kwargs):
        raise AssertionError("Real SSH/network connections are forbidden in these tests")

    monkeypatch.setattr(socket, "create_connection", deny_connection)
    for name in (
        "MESHCORE_SSH_HOST", "MESHCORE_SSH_USER", "MESHCORE_SSH_PASSWORD",
        "MESHCORE_SSH_HOST_KEY_SHA256",
    ):
        monkeypatch.delenv(name, raising=False)
    path = Path(__file__).resolve().parents[1] / "server.py"
    spec = importlib.util.spec_from_file_location("isolated_ssh_maintenance", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_mcp_registration_and_structured_result_without_connections(maintenance, monkeypatch):
    async def check():
        tools = await maintenance.mcp.list_tools()
        assert {tool.name for tool in tools} == {"ssh_host_key", "ssh_execute", "ssh_upload_file"}
        execute = next(tool for tool in tools if tool.name == "ssh_execute")
        assert execute.input_schema["properties"]["command"]["type"] == "string"
        monkeypatch.setattr(maintenance, "_discover_key", lambda: {"authenticated": False})
        result = await maintenance.mcp.call_tool("ssh_host_key", {})
        assert result.structured_content == {"authenticated": False}
        assert not result.is_error

    asyncio.run(check())


@pytest.mark.parametrize("fingerprint", ["", "SHA256:wrong"])
def test_host_key_failure_precedes_authentication_and_closes_transport(maintenance, monkeypatch, fingerprint):
    fake_transport = MagicMock()
    fake_transport.get_remote_server_key.return_value.asbytes.return_value = b"trusted key"
    monkeypatch.setattr(maintenance.socket, "create_connection", MagicMock())
    monkeypatch.setattr(maintenance.paramiko, "Transport", lambda sock: fake_transport)
    monkeypatch.setenv("MESHCORE_SSH_PASSWORD", "fixture-password")
    with pytest.raises(ValueError):
        with maintenance._transport(fingerprint):
            pytest.fail("Invalid fingerprint cannot yield an authenticated transport")
    fake_transport.auth_password.assert_not_called()
    if fingerprint:
        fake_transport.close.assert_called_once()


def test_valid_host_key_authenticates_without_fallback_then_closes(maintenance, monkeypatch):
    fake_transport = MagicMock()
    fake_key = fake_transport.get_remote_server_key.return_value
    fake_key.asbytes.return_value = b"trusted key"
    monkeypatch.setattr(maintenance.socket, "create_connection", MagicMock())
    monkeypatch.setattr(maintenance.paramiko, "Transport", lambda sock: fake_transport)
    monkeypatch.setenv("MESHCORE_SSH_PASSWORD", "fixture-password")
    with maintenance._transport(maintenance._fingerprint(fake_key)) as yielded:
        assert yielded is fake_transport
    fake_transport.auth_password.assert_called_once_with(maintenance.USER, "fixture-password", fallback=False)
    fake_transport.close.assert_called_once()


def test_execute_bounds_output_and_redacts_secrets(maintenance, monkeypatch):
    channel = MagicMock()
    channel.__enter__.return_value = channel
    channel.recv_ready.side_effect = [True, False]
    channel.recv.return_value = b"password=private-value " + b"x" * 1100
    channel.recv_stderr_ready.side_effect = [True, False]
    channel.recv_stderr.return_value = b"overflow"
    channel.exit_status_ready.return_value = True
    channel.recv_exit_status.return_value = 0
    transport = MagicMock()
    transport.__enter__.return_value = transport
    transport.open_session.return_value = channel
    monkeypatch.setattr(maintenance, "_transport", lambda key: transport)
    result = maintenance._execute("printf harmless", "SHA256:fixture", 1, 1024)
    assert result["exit_code"] == 0
    assert result["truncated"] and result["discarded_bytes"] > 0
    assert "private-value" not in result["stdout"]
    assert "[REDACTED]" in result["stdout"]
    assert result["stderr"] == ""
    assert "command" not in result


def test_upload_allows_staging_file_and_rejects_operational_archive(maintenance, monkeypatch, tmp_path):
    monkeypatch.setattr(maintenance, "WORKSPACE", tmp_path)
    file = tmp_path / "release.txt"
    file.write_bytes(b"release fixture")
    local, remote = maintenance._validate_upload(str(file), "/tmp/meshcore-staging-fixture/release.txt")
    assert local == file and str(remote).endswith("/release.txt")
    archive = tmp_path / "unsafe.tar"
    with tarfile.open(archive, "w") as package:
        entry = tarfile.TarInfo("data/private.json")
        entry.size = 2
        package.addfile(entry, io.BytesIO(b"{}"))
    with pytest.raises(ValueError, match="forbidden"):
        maintenance._validate_upload(str(archive), "/tmp/meshcore-staging-fixture/release.tar")


@pytest.mark.parametrize("remote", ["/etc/release.txt", "/tmp/meshcore-staging-fixture/../secret", "/tmp/meshcore-staging-fixture/.env"])
def test_upload_rejects_unsafe_remote_paths(maintenance, monkeypatch, tmp_path, remote):
    monkeypatch.setattr(maintenance, "WORKSPACE", tmp_path)
    file = tmp_path / "release.txt"
    file.write_bytes(b"release fixture")
    with pytest.raises(ValueError):
        maintenance._validate_upload(str(file), remote)


def test_streaming_file_hash_preserves_digest(maintenance):
    content = b"binary\x00fixture" * 12000
    assert maintenance._hash_file(io.BytesIO(content)) == hashlib.sha256(content).hexdigest()
