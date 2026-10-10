"""Installer contracts with isolated files and native commands replaced by mocks.

Never invoke the actual installer entrypoint, apt, pip, services, sudo or RF.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from scripts import check_runtime_dependencies as dependencies
from scripts import staged_update

ROOT = Path(__file__).resolve().parents[1]
BASH = shutil.which('bash') if os.name != 'nt' else r'C:\Program Files\Git\bin\bash.exe'
POWERSHELL = shutil.which('pwsh')


def source(path: str) -> str:
    return (ROOT / path).read_text(encoding='utf-8')


@pytest.mark.parametrize('missing', [entry[1] for entry in dependencies.DEPENDENCIES])
def test_partial_environment_does_not_pass_with_paho_alone(missing: str) -> None:
    def importer(module: str) -> object:
        if module == missing:
            raise ModuleNotFoundError(module)
        return object()

    versions = {entry[0]: '.'.join(map(str, entry[2])) for entry in dependencies.DEPENDENCIES}
    failures = dependencies.check_dependencies(importer, versions.__getitem__, profile='core')
    assert len(failures) == 1
    assert 'ModuleNotFoundError' in failures[0]


@pytest.mark.parametrize('old', [entry[0] for entry in dependencies.DEPENDENCIES])
def test_dependency_minimum_version_is_verified(old: str) -> None:
    versions = {entry[0]: '.'.join(map(str, entry[2])) for entry in dependencies.DEPENDENCIES}
    versions[old] = '0.1.0'
    failures = dependencies.check_dependencies(lambda module: object(), versions.__getitem__, profile='core')
    assert len(failures) == 1 and old in failures[0]


@pytest.mark.parametrize('profile', ['core', 'web'])
def test_complete_environment_passes(profile: str) -> None:
    versions = {entry[0]: '.'.join(map(str, entry[2])) for entry in dependencies.PROFILES[profile]}
    assert dependencies.check_dependencies(lambda module: object(), versions.__getitem__, profile=profile) == []


@pytest.mark.parametrize('missing', [entry[1] for entry in dependencies.WEB_DEPENDENCIES])
def test_web_profile_requires_each_asgi_dependency(missing: str) -> None:
    def importer(module: str) -> object:
        if module == missing:
            raise ModuleNotFoundError(module)
        return object()

    versions = {entry[0]: '.'.join(map(str, entry[2])) for entry in dependencies.PROFILES['web']}
    failures = dependencies.check_dependencies(importer, versions.__getitem__, profile='web')
    assert len(failures) == 1 and 'ModuleNotFoundError' in failures[0]


@pytest.mark.parametrize('distribution', [entry[0] for entry in dependencies.WEB_DEPENDENCIES])
@pytest.mark.parametrize('variant', ['older', 'newer', 'a1', 'rc1', '.dev1', '.post1', '+local'])
def test_web_profile_rejects_unevaluated_asgi_versions(distribution: str, variant: str) -> None:
    versions = {entry[0]: '.'.join(map(str, entry[2])) for entry in dependencies.PROFILES['web']}
    expected = versions[distribution]
    if variant == 'older':
        versions[distribution] = '0.0.1'
    elif variant == 'newer':
        major, minor, patch = map(int, expected.split('.'))
        versions[distribution] = f'{major}.{minor}.{patch + 1}'
    else:
        versions[distribution] = expected + variant
    failures = dependencies.check_dependencies(lambda module: object(), versions.__getitem__, profile='web')
    assert len(failures) == 1 and distribution in failures[0]
    assert f'requiere == {expected}' in failures[0]


def test_core_profile_accepts_newer_stable_dependency_versions() -> None:
    versions = {entry[0]: '999.0.0' for entry in dependencies.DEPENDENCIES}
    assert dependencies.check_dependencies(lambda module: object(), versions.__getitem__, profile='core') == []


@pytest.mark.parametrize('profile', ['', 'unknown', 'web-extra'])
def test_invalid_profile_fails_before_importing_packages(profile: str) -> None:
    imported: list[str] = []
    failures = dependencies.check_dependencies(lambda module: imported.append(module), profile=profile)
    assert len(failures) == 1 and 'Perfil' in failures[0]
    assert imported == []


def test_default_web_profile_cannot_be_downgraded_by_unknown_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('MESHCORE_PROFILE', 'misspelled-web')
    imported: list[str] = []
    assert dependencies.check_dependencies(lambda module: imported.append(module))
    assert imported == []


def test_explicit_web_profile_overrides_core_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('MESHCORE_PROFILE', 'core')
    versions = {entry[0]: '.'.join(map(str, entry[2])) for entry in dependencies.PROFILES['web']}
    imported: list[str] = []
    assert dependencies.check_dependencies(lambda module: imported.append(module), versions.__getitem__, profile='web') == []
    assert 'fastapi' in imported and 'starlette' in imported and 'h11' in imported


def test_dependency_import_failure_does_not_disclose_exception_values() -> None:
    def importer(module: str) -> object:
        raise RuntimeError('synthetic-api-key=do-not-log')

    failures = dependencies.check_dependencies(importer, profile='core')
    assert len(failures) == len(dependencies.DEPENDENCIES)
    assert all('RuntimeError' in failure and 'do-not-log' not in failure for failure in failures)


def test_cli_invalid_environment_profile_returns_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('MESHCORE_PROFILE', 'unknown')
    assert dependencies.main([]) == 1


def test_installers_always_verify_the_production_web_profile() -> None:
    for filename in ('install.sh', 'install.ps1'):
        probes = [line for line in source(filename).splitlines() if 'check_runtime_dependencies.py' in line]
        assert probes
        assert all('--profile web' in line for line in probes)


def create_release(path: Path, value: str) -> None:
    for relative in staged_update.REQUIRED:
        file_path = path / relative
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(value, encoding='utf-8')
    (path / 'scripts').mkdir(exist_ok=True)
    (path / 'scripts/probe.py').write_text(value, encoding='utf-8')


def test_incomplete_stage_never_changes_existing_installation(tmp_path: Path) -> None:
    target = tmp_path / 'installed'
    create_release(target, 'old')
    incoming = tmp_path / 'incoming'
    incoming.mkdir()
    with pytest.raises(ValueError, match='Release incompleto'):
        staged_update.prepare(incoming, target)
    assert (target / 'src/bridge_core.py').read_text() == 'old'
    assert not list(tmp_path.glob('.meshcore-stage-*'))


def test_copy_failure_before_stop_preserves_installation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target, incoming = tmp_path / 'installed', tmp_path / 'incoming'
    create_release(target, 'old')
    create_release(incoming, 'new')

    def failure(*args: object, **kwargs: object) -> None:
        raise OSError('copy failure')

    monkeypatch.setattr(staged_update.shutil, 'copytree', failure)
    with pytest.raises(OSError, match='copy failure'):
        staged_update.prepare(incoming, target)
    assert (target / 'src/bridge_core.py').read_text() == 'old'
    assert not list(tmp_path.glob('.meshcore-stage-*'))


@pytest.mark.parametrize('same_source', [False, True])
def test_stage_is_independent_and_preserves_operational_files(tmp_path: Path, same_source: bool) -> None:
    target = tmp_path / 'installed'
    create_release(target, 'old')
    incoming = target if same_source else tmp_path / 'incoming'
    if not same_source:
        create_release(incoming, 'new')
    operational = {'.env': b'SYNTHETIC_SECRET=abc\n', 'data/nodes.json': b'{"synthetic":1}', 'logs/bridge.log': b'past'}
    for relative, content in operational.items():
        path = target / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    stage = staged_update.prepare(incoming, target)
    assert not (stage / 'release/.env').exists()
    assert not (stage / 'release/data').exists()
    assert not (stage / 'release/logs').exists()
    staged_update.apply(stage)
    for relative, content in operational.items():
        assert (target / relative).read_bytes() == content
    assert (target / 'src/bridge_core.py').read_text() == ('old' if same_source else 'new')
    staged_update.rollback(stage)
    assert (target / 'src/bridge_core.py').read_text() == 'old'
    staged_update.rollback(stage)  # Recovery can safely be repeated.
    staged_update.finish(stage)
    assert not stage.exists()


def test_partial_switch_failure_restores_all_previous_components(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target, incoming = tmp_path / 'installed', tmp_path / 'incoming'
    create_release(target, 'old')
    create_release(incoming, 'new')
    stage = staged_update.prepare(incoming, target)
    original = os.replace
    failed = False

    def failure(src: str | Path, dst: str | Path) -> None:
        nonlocal failed
        if not failed and Path(src) == stage / 'release/config.py':
            failed = True
            raise OSError('rename failure after src replacement')
        original(src, dst)

    monkeypatch.setattr(staged_update.os, 'replace', failure)
    with pytest.raises(OSError, match='rename failure'):
        staged_update.apply(stage)
    assert failed
    for relative in staged_update.REQUIRED:
        assert (target / relative).read_text() == 'old'
    staged_update.finish(stage)


def test_staging_rejects_escaped_rollback_manifest(tmp_path: Path) -> None:
    target, incoming = tmp_path / 'installed', tmp_path / 'incoming'
    create_release(target, 'old')
    create_release(incoming, 'new')
    stage = staged_update.prepare(incoming, target)
    state = json.loads((stage / staged_update.MARKER).read_text())
    state['installed'] = ['../outside']
    (stage / staged_update.MARKER).write_text(json.dumps(state))
    with pytest.raises(ValueError, match='Componente de rollback'):
        staged_update.rollback(stage)


@pytest.mark.parametrize('invalid', [{}, {'target': '/'}, {'target': 'relative'}, {'target': 12}])
def test_staging_rejects_invalid_journal_schema(tmp_path: Path, invalid: dict[str, object]) -> None:
    target, incoming = tmp_path / 'installed', tmp_path / 'incoming'
    create_release(target, 'old')
    create_release(incoming, 'new')
    stage = staged_update.prepare(incoming, target)
    (stage / staged_update.MARKER).write_text(json.dumps(invalid))
    with pytest.raises(ValueError):
        staged_update.rollback(stage)


def test_relocated_venv_entrypoints_do_not_reference_deleted_staging(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target, incoming = tmp_path / 'installed', tmp_path / 'incoming'
    create_release(target, 'old')
    create_release(incoming, 'new')
    stage = staged_update.prepare(incoming, target)
    environment = target / 'venv'
    scripts = environment / ('Scripts' if os.name == 'nt' else 'bin')
    scripts.mkdir(parents=True)
    old_prefix = str(stage / 'release/venv')
    pip_script = scripts / 'pip'
    pip_script.write_bytes(f'#!{old_prefix}/bin/python\nprint("ready")\n'.encode())
    binary = scripts / 'binary'
    binary.write_bytes(b'\x00\xff')

    class FakeBuilder:
        def __init__(self, *, with_pip: bool, symlinks: bool) -> None:
            assert with_pip is False

        def create(self, location: str) -> None:
            assert Path(location) == environment
            (scripts / 'activate').write_text(str(environment))

    monkeypatch.setattr(staged_update.venv, 'EnvBuilder', FakeBuilder)
    staged_update.relocate_environment(stage)
    assert old_prefix.encode() not in pip_script.read_bytes()
    assert str(environment).encode() in pip_script.read_bytes()
    assert (scripts / 'activate').read_text() == str(environment)
    assert binary.read_bytes() == b'\x00\xff'


@pytest.mark.skipif(not BASH or not Path(BASH).exists(), reason='Bash unavailable for isolated shell contract')
@pytest.mark.parametrize('phase', ['pip', 'chromium', 'qa'])
def test_dev_propagates_mocked_native_failures(tmp_path: Path, phase: str) -> None:
    text = source('install.sh')
    block = text[text.index('if [[ "$ACTION" == "--dev" ]]'):text.index('# Render service identity')]
    project = tmp_path / 'project'
    installed = tmp_path / 'installed'
    for directory in (project / '.venv/bin', installed / 'venv/bin', project / 'scripts'):
        directory.mkdir(parents=True)
    for name in ('requirements-dev.txt', 'requirements.txt', 'scripts/run_quality_checks.py'):
        (project / name).write_text('mock', encoding='utf-8')
    mock = '''#!/usr/bin/env bash
if [[ "$*" == *"pip install"* && "$FAIL_PHASE" == "pip" ]]; then exit 17; fi
if [[ "$*" == *"playwright install"* && "$FAIL_PHASE" == "chromium" ]]; then exit 17; fi
if [[ "$*" == *"run_quality_checks.py"* && "$FAIL_PHASE" == "qa" ]]; then exit 17; fi
exit 0
'''
    for path in (project / '.venv/bin/python', installed / 'venv/bin/python', installed / 'venv/bin/pip'):
        path.write_text(mock, encoding='utf-8')
        path.chmod(0o755)
    runner = tmp_path / 'dev-contract.sh'
    runner.write_text('set -Eeuo pipefail\nACTION=--dev\n' + block, encoding='utf-8')
    env = dict(os.environ, CURRENT_DIR=project.as_posix(), INSTALL_DIR=installed.as_posix(), FAIL_PHASE=phase)
    result = subprocess.run([str(BASH), str(runner)], env=env, capture_output=True, text=True, timeout=20)
    assert result.returncode == 17, result.stdout + result.stderr
    assert '[OK] Verificaciones ejecutadas' not in result.stdout


def test_update_prepares_and_checks_before_stop_and_keeps_rollback() -> None:
    text = source('install.sh')
    block = text[text.index('if [[ "$ACTION" == "--update" ]]'):text.index('# 4. Instalación')]
    assert block.index('prepare "$CURRENT_DIR"') < block.index('systemctl stop')
    assert block.index('check_runtime_dependencies.py') < block.index('systemctl stop')
    assert block.index('compileall') < block.index('systemctl stop')
    assert 'trap rollback_update ERR INT TERM' in block
    assert 'systemd.previous' in block and 'rollback "$STAGE_DIR"' in block
    assert 'rm -rf "$INSTALL_DIR/src"' not in block
    assert '>> "$INSTALL_DIR/.env"' not in block
    assert 'mosquitto' not in block


@pytest.mark.skipif(not BASH or not Path(BASH).exists(), reason='Bash unavailable for isolated install contract')
@pytest.mark.parametrize('invoker', ['root', 'operator'])
def test_complete_install_configures_identity_before_ownership_and_service(
    tmp_path: Path, invoker: str,
) -> None:
    """Run only the fresh-install body on fixtures, replacing all system operations."""
    text = source('install.sh')
    definitions = text[text.index('configure_service_identity() {'):text.index('# --update stages')]
    block = text[text.index('# 4. Instalación Completa'):]
    project, installed = tmp_path / 'project', tmp_path / 'installed'
    create_release(project, 'fixture')
    (project / 'docs').mkdir()
    (project / 'docs/sample.md').write_text('fixture')
    (project / 'pyproject.toml').write_text('fixture')
    (project / '.env.example').write_text('SERIAL_PORT=AUTO\n')
    (project / 'meshcore-bridge.service').write_text(source('meshcore-bridge.service'))
    (installed / 'venv/bin').mkdir(parents=True)
    (installed / '.env').write_text('SYNTHETIC_PREF=unchanged\n')
    interpreter = installed / 'venv/bin/python'
    interpreter.write_text('#!/usr/bin/env bash\nexit 0\n')
    interpreter.chmod(0o755)
    systemd = tmp_path / 'systemd'
    systemd.mkdir()
    mosquitto = tmp_path / 'mosquitto'
    block = block.replace('MOSQUITTO_CONF_DIR="/etc/mosquitto/conf.d"', f'MOSQUITTO_CONF_DIR="{mosquitto.as_posix()}"')
    mocks = '''
ACCOUNT_CREATED=0
apt-get() { :; }
systemctl() { :; }
python3() { :; }
sleep() { :; }
hostname() { echo 127.0.0.1; }
compgen() { return 1; }
rm() { :; }
useradd() { ACCOUNT_CREATED=1; }
usermod() { echo "usermod $*" >> "$CALL_LOG"; }
getent() { return 0; }
id() {
    if [[ "$SERVICE_USER" == "meshcore" && "$ACCOUNT_CREATED" == "0" ]]; then return 1; fi
    if [[ "${1:-}" == "-u" ]]; then echo 1001;
    elif [[ "${1:-}" == "-gn" ]]; then echo "$SERVICE_USER";
    else echo "mock identity"; fi
}
chown() {
    echo "chown $*" >> "$CALL_LOG"
    [[ -n "$SERVICE_GROUP" ]] || return 19
    if [[ "$SERVICE_USER" == "meshcore" ]]; then [[ "$ACCOUNT_CREATED" == "1" ]] || return 19; fi
}
'''
    runner = tmp_path / 'fresh-contract.sh'
    runner.write_text('set -Eeuo pipefail\nRED=""; GREEN=""; YELLOW=""; BLUE=""; CYAN=""; NC=""\nSERVICE_GROUP=""\n' + mocks + definitions + block, encoding='utf-8')
    service_user = 'meshcore' if invoker == 'root' else invoker
    env = dict(os.environ, CURRENT_DIR=project.as_posix(), INSTALL_DIR=installed.as_posix(),
               TARGET_USER=invoker, SERVICE_USER=service_user, SYSTEMD_DIR=systemd.as_posix(),
               SERVICE_NAME='meshcore-bridge.service', CALL_LOG=(tmp_path / 'calls.log').as_posix())
    result = subprocess.run([str(BASH), str(runner)], env=env, capture_output=True, encoding='utf-8', errors='replace', timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr
    unit = (systemd / 'meshcore-bridge.service').read_text()
    assert f'User={service_user}\n' in unit and f'Group={service_user}\n' in unit
    assert (installed / '.env').read_text() == 'SYNTHETIC_PREF=unchanged\n'


def test_service_identity_and_shutdown_contract() -> None:
    unit = source('meshcore-bridge.service')
    assert 'User=root' not in unit
    assert 'Group=meshcore' in unit and 'KillMode=control-group' in unit
    assert 'NoNewPrivileges=true' in unit
    installer = source('install.sh')
    assert 'MESHCORE_SERVICE_USER:-$TARGET_USER' in installer
    assert 'SUDO_USER' in installer and 'id -u "$SERVICE_USER"' in installer
    assert 'getent group "$group"' in installer and 'usermod -aG "$group"' in installer
    assert 'render_service "$INSTALL_DIR/meshcore-bridge.service"' in installer


@pytest.mark.skipif(not POWERSHELL, reason='PowerShell unavailable for syntax parser')
def test_powershell_syntax_and_complete_probe(tmp_path: Path) -> None:
    # Parsing creates no environment and invokes no native command.
    program = "$tokens=$null; $errors=$null; [System.Management.Automation.Language.Parser]::ParseFile($args[0],[ref]$tokens,[ref]$errors) | Out-Null; if($errors.Count){$errors | Out-String | Write-Output; exit 1}"
    script = tmp_path / 'parse.ps1'
    script.write_text(program)
    result = subprocess.run([str(POWERSHELL), '-NoProfile', '-File', str(script), str(ROOT / 'install.ps1')], capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr
    text = source('install.ps1')
    assert 'site-packages\\paho' not in text
    assert 'Test-RuntimeDependencies -PythonPath $PythonPath' in text
    assert 'check_runtime_dependencies.py' in text
    assert 'run_interactive_demo.py' in text
