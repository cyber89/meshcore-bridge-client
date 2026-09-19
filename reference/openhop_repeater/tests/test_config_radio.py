from types import SimpleNamespace

from repeater.config import BaselineCrcCounterRadio, load_config


def test_baseline_crc_counter_radio_reports_delta_from_initial_raw_count():
    raw = SimpleNamespace(crc_error_count=20_000, frequency=869_618_000)
    radio = BaselineCrcCounterRadio(raw)

    assert radio.frequency == 869_618_000
    assert radio.crc_error_count == 0

    raw.crc_error_count = 20_003

    assert radio.crc_error_count == 3


def test_baseline_crc_counter_radio_handles_delayed_modem_counter():
    raw = SimpleNamespace(crc_error_count=0)
    radio = BaselineCrcCounterRadio(raw)

    assert radio.crc_error_count == 0

    raw.crc_error_count = 145
    assert radio.crc_error_count == 0

    raw.crc_error_count = 148
    assert radio.crc_error_count == 3


def test_load_config_prefers_openhop_env_names(tmp_path, monkeypatch):
    legacy_path = tmp_path / "legacy.yaml"
    openhop_path = tmp_path / "openhop.yaml"
    legacy_path.write_text("repeater:\n  identity_key: legacy\n", encoding="utf-8")
    openhop_path.write_text("repeater:\n  identity_key: openhop\n", encoding="utf-8")

    monkeypatch.setenv("PYMC_REPEATER_CONFIG", str(legacy_path))
    monkeypatch.setenv("OPENHOP_REPEATER_CONFIG", str(openhop_path))
    monkeypatch.setenv("PYMC_REPEATER_LOG_LEVEL", "WARNING")
    monkeypatch.setenv("OPENHOP_REPEATER_LOG_LEVEL", "DEBUG")

    config = load_config()

    assert config["repeater"]["identity_key"] == "openhop"
    assert config["logging"]["level"] == "DEBUG"
