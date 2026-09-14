"""
Unit tests for RepeaterManager (Airtime Cooldowns, Command Formatting & Analysis).
"""


from src.repeater_manager import RepeaterManager


def test_repeater_manager_airtime_cooldown() -> None:
    mgr = RepeaterManager(min_cmd_interval_s=2.0, min_telemetry_interval_s=5.0)
    rep_pk = "aabbcc112233"

    # Inicialmente sin comandos previos, debe permitir envío
    can_send, rem = mgr.check_airtime_cooldown(rep_pk, is_full_query=False)
    assert can_send is True
    assert rem == 0.0

    # Registrar comando enviado
    mgr.record_command_sent(rep_pk, is_full_query=False)

    # Inmediatamente después, debe estar en cooldown
    can_send_after, rem_after = mgr.check_airtime_cooldown(rep_pk, is_full_query=False)
    assert can_send_after is False
    assert rem_after > 0.0

    # Registrar consulta completa de telemetría
    mgr.record_command_sent(rep_pk, is_full_query=True)
    can_telem, rem_telem = mgr.check_airtime_cooldown(rep_pk, is_full_query=True)
    assert can_telem is False
    assert rem_telem > 0.0


def test_build_repeater_query_commands() -> None:
    mgr = RepeaterManager()

    # Comandos simples de consulta
    assert mgr.build_repeater_command_payload("stats", {}) == "stats-core"
    assert mgr.build_repeater_command_payload("ver", {}) == "ver"
    assert mgr.build_repeater_command_payload("version", {}) == "ver"
    assert mgr.build_repeater_command_payload("neighbors", {}) == "neighbors"
    assert mgr.build_repeater_command_payload("bat", {}) == "get pwrmgt.bootmv"
    assert mgr.build_repeater_command_payload("clock", {}) == "clock"
    assert mgr.build_repeater_command_payload("uptime", {}) == "get uptime"
    assert mgr.build_repeater_command_payload("pos", {}) == "get lat"


def test_build_repeater_radio_commands() -> None:
    mgr = RepeaterManager()

    # set_tx_power
    pwr_cmd = mgr.build_repeater_command_payload("set_tx_power", {"tx_power": 18})
    assert pwr_cmd == "set tx 18"

    # set_freq
    freq_cmd = mgr.build_repeater_command_payload("set_freq", {"freq": 915.0})
    assert freq_cmd == "set freq 915.0"

    # set_bw
    bw_cmd = mgr.build_repeater_command_payload("set_bw", {"bw": 250})
    assert bw_cmd == "set bw 250"


def test_build_repeater_location_and_security_commands() -> None:
    mgr = RepeaterManager()

    # set_coords
    pos_cmd = mgr.build_repeater_command_payload("set_coords", {"lat": -33.45, "lon": -70.66})
    assert pos_cmd.startswith("set pos -33.45 -70.66")

    # set_name
    name_cmd = mgr.build_repeater_command_payload("set_name", {"name": "Rep-Cumbre"})
    assert name_cmd == "set name Rep-Cumbre"

    # login / auth
    login_cmd = mgr.build_repeater_command_payload("login", {"pin": "1234"})
    assert login_cmd == "login 1234"
