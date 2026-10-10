"""Explicit SSH maintenance over MCP stdio, restricted to the authorized station."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import os
import re
import shlex
import socket
import sys
import tarfile
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path, PurePosixPath
from typing import Any, BinaryIO

if (
    sys.implementation.name != "cpython"
    or sys.version_info[:2] < (3, 11)
):
    raise RuntimeError("CPython >=3.11 is required for SSH maintenance")

import paramiko  # noqa: E402 - validate the runtime before loading third-party SDKs
from mcp.server.mcpserver import MCPServer  # noqa: E402

HOST = "192.168.0.242"
USER = "root"
WORKSPACE = Path(__file__).resolve().parents[2]
CONNECT_TIMEOUT = 10.0
MAX_UPLOAD_BYTES = 100 * 1024 * 1024
SENSITIVE_NAME = r"[\w.-]*(?:password|passwd|token|secret|psk|api_key|private_key)[\w.-]*"
SENSITIVE_FIELD = re.compile(
    rf"(?i)([\"']?{SENSITIVE_NAME}[\"']?\s*[:=]\s*)(\"[^\"\n]*\"|'[^'\n]*'|[^\s,;}}\n]+)"
)
PRIVATE_KEY = re.compile(
    r"-----BEGIN [^-\n]*PRIVATE KEY-----.*?(?:-----END [^-\n]*PRIVATE KEY-----|\Z)",
    re.DOTALL,
)
mcp = MCPServer("MeshCore station SSH maintenance")


def redact(text: str) -> str:
    """Heuristic redaction; operators must still choose commands that omit secrets."""
    text = PRIVATE_KEY.sub("[REDACTED PRIVATE KEY]", text)
    password = os.getenv("MESHCORE_SSH_PASSWORD", "")
    if password:
        text = text.replace(password, "[REDACTED]")
    return SENSITIVE_FIELD.sub(lambda match: match.group(1) + '"[REDACTED]"', text)


def _validate_target() -> None:
    if os.getenv("MESHCORE_SSH_HOST", HOST) != HOST:
        raise ValueError("This MCP permits only the authorized station host")
    if os.getenv("MESHCORE_SSH_USER", USER) != USER:
        raise ValueError("This MCP permits only the authorized station user")


def _fingerprint(key: paramiko.PKey) -> str:
    digest = hashlib.sha256(key.asbytes()).digest()
    return "SHA256:" + base64.b64encode(digest).decode("ascii").rstrip("=")


@contextmanager
def _transport(expected_host_key: str | None = None) -> Iterator[paramiko.Transport]:
    """Check the negotiated key before sending any authentication material."""
    _validate_target()
    expected = expected_host_key or os.getenv("MESHCORE_SSH_HOST_KEY_SHA256", "")
    if expected_host_key is not None and not expected.startswith("SHA256:"):
        raise ValueError("An expected SHA256 host-key fingerprint is required")
    with socket.create_connection((HOST, 22), timeout=CONNECT_TIMEOUT) as sock:
        transport = paramiko.Transport(sock)
        try:
            transport.banner_timeout = CONNECT_TIMEOUT
            transport.auth_timeout = CONNECT_TIMEOUT
            transport.start_client(timeout=CONNECT_TIMEOUT)
            if expected_host_key is not None:
                actual = _fingerprint(transport.get_remote_server_key())
                if not hmac.compare_digest(actual, expected):
                    raise ValueError("SSH host key differs from the pinned fingerprint; authentication refused")
                password = os.getenv("MESHCORE_SSH_PASSWORD", "")
                if not password:
                    raise ValueError("MESHCORE_SSH_PASSWORD must be provided in process memory")
                transport.auth_password(USER, password, fallback=False)
            yield transport
        finally:
            transport.close()


def _discover_key() -> dict[str, Any]:
    with _transport() as transport:
        key = transport.get_remote_server_key()
        return {"host": HOST, "port": 22, "algorithm": key.get_name(), "sha256": _fingerprint(key), "authenticated": False}


@mcp.tool()
async def ssh_host_key() -> dict[str, Any]:
    """Discover the station SSH key without authentication; discovery alone is not identity proof."""
    return await asyncio.to_thread(_discover_key)


def _execute(command: str, expected_host_key: str, timeout_seconds: int, max_output_bytes: int) -> dict[str, Any]:
    if not command.strip() or "\x00" in command:
        raise ValueError("A non-empty command without NUL bytes is required")
    if not 1 <= timeout_seconds <= 120:
        raise ValueError("timeout_seconds must be between 1 and 120")
    if not 1024 <= max_output_bytes <= 262144:
        raise ValueError("max_output_bytes must be between 1024 and 262144")
    stdout = bytearray()
    stderr = bytearray()
    discarded = 0
    timed_out = False
    exit_code: int | None = None
    # coreutils timeout prevents an ordinary foreground command outliving the local wait.
    wrapped = f"timeout --signal=TERM --kill-after=5s {timeout_seconds}s sh -c {shlex.quote(command)}"
    with _transport(expected_host_key) as transport:
        with transport.open_session(timeout=CONNECT_TIMEOUT) as channel:
            channel.settimeout(CONNECT_TIMEOUT)
            channel.exec_command(wrapped)
            deadline = time.monotonic() + timeout_seconds + 6
            while True:
                for ready, receive, destination in (
                    (channel.recv_ready, channel.recv, stdout),
                    (channel.recv_stderr_ready, channel.recv_stderr, stderr),
                ):
                    if ready():
                        chunk = receive(32768)
                        remaining = max(0, max_output_bytes - len(stdout) - len(stderr))
                        destination.extend(chunk[:remaining])
                        discarded += max(0, len(chunk) - remaining)
                if channel.exit_status_ready() and not channel.recv_ready() and not channel.recv_stderr_ready():
                    exit_code = channel.recv_exit_status()
                    timed_out = exit_code in (124, 137)
                    break
                if time.monotonic() >= deadline:
                    timed_out = True
                    break
                time.sleep(0.02)
    return {
        "host": HOST,
        "exit_code": exit_code,
        "timed_out": timed_out,
        "truncated": discarded > 0,
        "discarded_bytes": discarded,
        "stdout": redact(stdout.decode("utf-8", errors="replace")),
        "stderr": redact(stderr.decode("utf-8", errors="replace")),
    }


@mcp.tool()
async def ssh_execute(command: str, expected_host_key: str = "", timeout_seconds: int = 30, max_output_bytes: int = 65536) -> dict[str, Any]:
    """Run an explicit authorized shell command on the station; commands can mutate it. No automatic RF checks."""
    return await asyncio.to_thread(_execute, command, expected_host_key, timeout_seconds, max_output_bytes)


def _forbidden_parts(parts: tuple[str, ...]) -> bool:
    forbidden = {"data", "logs", ".git", ".aws", ".codex", ".venv", "venv", ".env"}
    return any(
        part.lower() in forbidden
        or (part.lower().startswith(".env.") and part.lower() != ".env.example")
        for part in parts
    )


def _validate_upload(local_path: str, remote_path: str) -> tuple[Path, PurePosixPath]:
    local = Path(local_path)
    if not local.is_absolute():
        raise ValueError("local_path must explicitly name an absolute workspace file")
    local = local.resolve(strict=True)
    try:
        relative = local.relative_to(WORKSPACE)
    except ValueError as exc:
        raise ValueError("Uploads must remain inside the project workspace") from exc
    if _forbidden_parts(relative.parts) or not local.is_file():
        raise ValueError("Operational data, credentials and environment files cannot be uploaded")
    if local.stat().st_size > MAX_UPLOAD_BYTES:
        raise ValueError("Upload exceeds the 100 MiB maintenance limit")
    if tarfile.is_tarfile(local):
        with tarfile.open(local) as archive:
            for member in archive:
                member_path = PurePosixPath(member.name)
                if member_path.is_absolute() or ".." in member_path.parts or _forbidden_parts(member_path.parts):
                    raise ValueError("Archive contains forbidden or unsafe paths")
                if member.issym() or member.islnk() or not (member.isfile() or member.isdir()):
                    raise ValueError("Only regular files and directories are permitted inside an uploaded archive")
    remote = PurePosixPath(remote_path)
    if not remote.is_absolute() or ".." in remote.parts or len(remote.parts) < 4:
        raise ValueError("remote_path must be an absolute file below a staging directory")
    permitted = remote.parts[1] in {"tmp", "opt"} and remote.parts[2].startswith("meshcore-staging-")
    if not permitted or _forbidden_parts(remote.parts[3:]):
        raise ValueError("Destination must be beneath /tmp/meshcore-staging-* or /opt/meshcore-staging-*")
    return local, remote


def _upload(local_path: str, remote_path: str, expected_host_key: str) -> dict[str, Any]:
    local, remote = _validate_upload(local_path, remote_path)
    with local.open("rb") as source:
        digest = _hash_file(source)
        source.seek(0)
        with _transport(expected_host_key) as transport:
            with paramiko.SFTPClient.from_transport(transport) as sftp:
                sftp.get_channel().settimeout(CONNECT_TIMEOUT)
                # Resolve existing parent first: reject symlinks leading outside staging.
                normalized = PurePosixPath(sftp.normalize(str(remote.parent)))
                if normalized != remote.parent:
                    raise ValueError("Staging parent must exist without symlink redirection")
                try:
                    sftp.lstat(str(remote))
                except FileNotFoundError:
                    pass
                else:
                    raise ValueError("Upload refuses to overwrite an existing remote file")
                with sftp.open(str(remote), "wx") as destination:
                    deadline = time.monotonic() + 120
                    while chunk := source.read(65536):
                        if time.monotonic() >= deadline:
                            raise TimeoutError("SFTP upload exceeded its 120-second deadline; partial staging file may remain")
                        destination.write(chunk)
                sftp.chmod(str(remote), 0o600)
    return {"host": HOST, "remote_path": str(remote), "bytes": local.stat().st_size, "local_sha256": digest}


def _hash_file(source: BinaryIO) -> str:
    """Compute a streaming digest using the native CPython file helper."""
    return hashlib.file_digest(source, "sha256").hexdigest()


@mcp.tool()
async def ssh_upload_file(local_path: str, remote_path: str, expected_host_key: str = "") -> dict[str, Any]:
    """Upload one explicit workspace file into an existing station staging directory; never overwrite."""
    return await asyncio.to_thread(_upload, local_path, remote_path, expected_host_key)


if __name__ == "__main__":
    mcp.run(transport="stdio")
