"""Isolated contracts for installer hardening; never run a production installer."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
BASH = shutil.which("bash") if os.name != "nt" else r"C:\Program Files\Git\bin\bash.exe"
POWERSHELL = shutil.which("pwsh") or shutil.which("powershell")


def installer_function(name: str, next_marker: str) -> str:
    text = (ROOT / "install.sh").read_text(encoding="utf-8")
    return text[text.index(f"{name}() {{"):text.index(next_marker, text.index(f"{name}() {{"))]


@pytest.mark.skipif(not BASH or not Path(BASH).is_file(), reason="Bash unavailable")
def test_existing_destination_is_rejected_before_system_changes(tmp_path: Path) -> None:
    text = (ROOT / "install.sh").read_text(encoding="utf-8")
    guard = text[text.index("# A fresh installation"):text.index("# 2. Uninstall")]
    destination = tmp_path / "existing"
    destination.mkdir()
    preserved = destination / "operator-state"
    preserved.write_text("keep", encoding="utf-8")
    script = tmp_path / "guard.sh"
    script.write_text(
        "set -Eeuo pipefail\nprint_fail(){ :; }; print_info(){ :; }\n"
        + guard + '\nprintf changed > "$INSTALL_DIR/modified"\n', encoding="utf-8", newline="\n",
    )
    result = subprocess.run(
        [str(BASH), str(script)], capture_output=True, text=True, timeout=15,
        env=dict(os.environ, ACTION="", INSTALL_DIR=destination.as_posix()),
    )
    assert result.returncode != 0
    assert preserved.read_text(encoding="utf-8") == "keep"
    assert not (destination / "modified").exists()


@pytest.mark.skipif(not BASH or not Path(BASH).is_file(), reason="Bash unavailable")
def test_initial_configuration_inserts_missing_keys_with_private_permissions(tmp_path: Path) -> None:
    template, destination = tmp_path / "template", tmp_path / "station.env"
    template.write_text("# Preserve settings\nDATA_DIR=custom-data\n", encoding="utf-8")
    script = tmp_path / "configuration.sh"
    script.write_text(
        "set -Eeuo pipefail\numask 022\n"
        + installer_function("write_initial_configuration", "# Service identity")
        + '\nwrite_initial_configuration "$TEMPLATE" "$DESTINATION"\n',
        encoding="utf-8", newline="\n",
    )
    result = subprocess.run(
        [str(BASH), str(script)], capture_output=True, text=True, timeout=15,
        env=dict(os.environ, PYTHON_RUNTIME=Path(sys.executable).as_posix(), TEMPLATE=template.as_posix(),
                 DESTINATION=destination.as_posix(), DETECTED_PORT="/dev/ttyUSB0",
                 MQTT_BRIDGE_USER="meshcore_bridge", MQTT_BRIDGE_PASS="synthetic-secret"),
    )
    assert result.returncode == 0, result.stderr
    content = destination.read_text(encoding="utf-8")
    assert "DATA_DIR=custom-data" in content
    assert "SERIAL_PORT=/dev/ttyUSB0" in content
    assert "MQTT_USER=meshcore_bridge" in content
    assert "MQTT_PASSWORD=synthetic-secret" in content
    if os.name != "nt":
        assert destination.stat().st_mode & 0o777 == 0o600
    # A second initialization must preserve the original file, not rewrite it.
    second = subprocess.run(
        [str(BASH), str(script)], capture_output=True, text=True, timeout=15,
        env=dict(os.environ, PYTHON_RUNTIME=Path(sys.executable).as_posix(), TEMPLATE=template.as_posix(),
                 DESTINATION=destination.as_posix(), DETECTED_PORT="/dev/ttyUSB1",
                 MQTT_BRIDGE_USER="replacement", MQTT_BRIDGE_PASS="replacement"),
    )
    assert second.returncode != 0
    assert destination.read_text(encoding="utf-8") == content


@pytest.mark.skipif(not BASH or not Path(BASH).is_file(), reason="Bash unavailable")
def test_broker_password_failure_prevents_start(tmp_path: Path) -> None:
    script = tmp_path / "broker.sh"
    script.write_text(
        'set -Eeuo pipefail\nprint_ok(){ :; }; print_fail(){ :; }\n'
        'getent(){ :; }; chown(){ :; }\n'
        'mosquitto_passwd(){ return 23; }\n'
        'systemctl(){ printf called >> "$SERVICE_CALLS"; }\n'
        + installer_function("configure_local_broker", "# Create a private initial configuration")
        + '\nconfigure_local_broker\n', encoding="utf-8", newline="\n",
    )
    result = subprocess.run(
        [str(BASH), str(script)], capture_output=True, text=True, timeout=15,
        env=dict(os.environ, MOSQUITTO_CONF_DIR=(tmp_path / "broker").as_posix(),
                 MQTT_BRIDGE_USER="meshcore_bridge", MQTT_CLIENT_USER="meshcore_client",
                 MQTT_BRIDGE_PASS="synthetic", MQTT_CLIENT_PASS="synthetic-client",
                 SERVICE_CALLS=(tmp_path / "service-calls").as_posix()),
    )
    assert result.returncode == 23, result.stderr
    assert not (tmp_path / "service-calls").exists()


@pytest.mark.skipif(not BASH or not Path(BASH).is_file(), reason="Bash unavailable")
@pytest.mark.parametrize("runtime_body", ["exit 17", "exit 0", "printf predictable"])
def test_secure_password_generation_has_no_fixed_fallback(tmp_path: Path, runtime_body: str) -> None:
    runtime = tmp_path / "runtime"
    runtime.write_text("#!/usr/bin/env bash\n" + runtime_body + "\n", encoding="utf-8", newline="\n")
    runtime.chmod(0o755)
    script = tmp_path / "password.sh"
    script.write_text(
        'set -Eeuo pipefail\nprint_fail(){ :; }\n'
        + installer_function("generate_mqtt_password", "configure_local_broker() {")
        + '\ngenerate_mqtt_password\n', encoding="utf-8", newline="\n",
    )
    result = subprocess.run(
        [str(BASH), str(script)], capture_output=True, text=True, timeout=15,
        env=dict(os.environ, PYTHON_RUNTIME=runtime.as_posix()),
    )
    assert result.returncode != 0
    assert result.stdout == ""


@pytest.mark.skipif(not POWERSHELL, reason="PowerShell unavailable")
def test_single_serial_port_remains_complete_string(tmp_path: Path) -> None:
    text = (ROOT / "install.ps1").read_text(encoding="utf-8")
    block = text[text.index("$DetectedPorts = @()"):text.index("# 5. Create configuration")]
    block = block.replace("[System.IO.Ports.SerialPort]::GetPortNames()", "@('COM3')")
    script = tmp_path / "serial-selection.ps1"
    script.write_text(
        "function Write-Success { param($Message) }; function Write-Warn { param($Message) }\n"
        + block + '\nWrite-Output $DefaultPort\n', encoding="utf-8",
    )
    result = subprocess.run(
        [str(POWERSHELL), "-NoProfile", "-File", str(script)],
        capture_output=True, text=True, timeout=15,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "COM3"
