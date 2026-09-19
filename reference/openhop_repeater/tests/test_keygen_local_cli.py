import hashlib
import json
from unittest.mock import patch

import pytest

from repeater import keygen
from repeater import local_cli


class _Resp:
    def __init__(self, payload):
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return json.dumps(self._payload).encode()


def test_generate_meshcore_keypair_clamps_scalar_and_shapes_output():
    seed = b"\xff" * 32
    captured = {}

    def _fake_scalarmult(scalar_bytes):
        captured["scalar"] = scalar_bytes
        return b"\xaa" * 32

    with (
        patch("repeater.keygen.secrets.token_bytes", return_value=seed),
        patch(
            "repeater.keygen.crypto_scalarmult_ed25519_base_noclamp", side_effect=_fake_scalarmult
        ),
    ):
        pub, priv = keygen.generate_meshcore_keypair()

    digest = hashlib.sha512(seed).digest()
    expected = bytearray(digest[:32])
    expected[0] &= 248
    expected[31] &= 63
    expected[31] |= 64

    assert pub == b"\xaa" * 32
    assert len(pub) == 32
    assert len(priv) == 64
    assert captured["scalar"] == bytes(expected)
    assert priv[:32] == bytes(expected)
    assert priv[32:] == digest[32:64]


def test_generate_vanity_key_success_after_multiple_attempts_and_none_on_limit():
    pairs = [
        (bytes.fromhex("11" * 32), b"p" * 64),
        (bytes.fromhex("22" * 32), b"q" * 64),
        (bytes.fromhex("ab" + "33" * 31), b"r" * 64),
    ]

    with patch("repeater.keygen.generate_meshcore_keypair", side_effect=pairs):
        out = keygen.generate_vanity_key(prefix="AB", max_iterations=10)

    assert out is not None
    assert out["attempts"] == 3
    assert out["public_hex"].startswith("ab")
    assert out["private_hex"] == (b"r" * 64).hex()

    with patch(
        "repeater.keygen.generate_meshcore_keypair",
        return_value=(bytes.fromhex("00" * 32), b"z" * 64),
    ):
        miss = keygen.generate_vanity_key(prefix="FF", max_iterations=2)
    assert miss is None


def test_load_config_reads_yaml_from_explicit_path(tmp_path):
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text("http:\n  port: 8123\n")

    cfg = local_cli._load_config(str(cfg_path))
    assert cfg["http"]["port"] == 8123


def test_load_config_returns_empty_when_not_found(tmp_path):
    cfg = local_cli._load_config(str(tmp_path / "missing.yaml"))
    assert cfg == {}


def test_run_client_cli_exits_when_auth_missing_or_connection_fails(capsys):
    # Empty password path -> auth fail -> sys.exit(1)
    with pytest.raises(SystemExit):
        local_cli.run_client_cli(password="")

    out1 = capsys.readouterr().out
    assert "Authentication failed" in out1

    # URLError during auth should exit with connection message.
    import urllib.error

    with (
        patch("urllib.request.urlopen", side_effect=urllib.error.URLError("down")),
        pytest.raises(SystemExit),
    ):
        local_cli.run_client_cli(password="secret")

    out2 = capsys.readouterr().out
    assert "Cannot connect to repeater" in out2


def test_run_client_cli_happy_path_and_command_error_branch(capsys):
    responses = [
        _Resp({"token": "jwt-token"}),
        _Resp({"success": True, "data": {"reply": "pong"}}),
        _Resp({"success": False, "error": "bad cmd"}),
    ]

    with (
        patch("urllib.request.urlopen", side_effect=responses),
        patch("builtins.input", side_effect=["ping", "oops", "exit"]),
    ):
        local_cli.run_client_cli(password="secret", port=9000)

    out = capsys.readouterr().out
    assert "connected to http://127.0.0.1:9000" in out
    assert "pong" in out
    assert "Error: bad cmd" in out


def test_run_client_cli_handles_runtime_connection_error_during_command(capsys):
    import urllib.error

    def _urlopen_side_effect(*_args, **_kwargs):
        if not hasattr(_urlopen_side_effect, "count"):
            _urlopen_side_effect.count = 0
        _urlopen_side_effect.count += 1
        if _urlopen_side_effect.count == 1:
            return _Resp({"token": "jwt-token"})
        raise urllib.error.URLError("timeout")

    with (
        patch("urllib.request.urlopen", side_effect=_urlopen_side_effect),
        patch("builtins.input", side_effect=["status", "quit"]),
    ):
        local_cli.run_client_cli(password="secret")

    out = capsys.readouterr().out
    assert "Connection error: timeout" in out


def test_main_uses_config_defaults_and_cli_overrides(capsys):
    class _Args:
        config = "/tmp/cfg.yaml"
        host = None
        port = None

    config = {
        "repeater": {"security": {"admin_password": "pw"}},
        "http": {"port": 8765},
    }

    with (
        patch("argparse.ArgumentParser.parse_args", return_value=_Args()),
        patch("repeater.local_cli._load_config", return_value=config),
        patch("repeater.local_cli.run_client_cli") as run_cli,
    ):
        local_cli.main()

    run_cli.assert_called_once_with(host="127.0.0.1", port=8765, password="pw")

    class _ArgsOverride:
        config = "/tmp/cfg.yaml"
        host = "10.0.0.9"
        port = 9999

    with (
        patch("argparse.ArgumentParser.parse_args", return_value=_ArgsOverride()),
        patch("repeater.local_cli._load_config", return_value=config),
        patch("repeater.local_cli.run_client_cli") as run_cli2,
    ):
        local_cli.main()

    run_cli2.assert_called_once_with(host="10.0.0.9", port=9999, password="pw")

    config_missing_pw = {"repeater": {"security": {}}, "http": {"port": 8765}}
    with (
        patch("argparse.ArgumentParser.parse_args", return_value=_Args()),
        patch("repeater.local_cli._load_config", return_value=config_missing_pw),
        patch("sys.exit", side_effect=SystemExit(1)) as exit_mock,
        pytest.raises(SystemExit),
    ):
        local_cli.main()

    exit_mock.assert_called_once_with(1)
    out = capsys.readouterr().out
    assert "No admin_password found" in out
