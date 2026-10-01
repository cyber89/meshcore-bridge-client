"""User-controlled CSV fields must stay text when opened in a spreadsheet."""

import csv
import io

import pytest

from src.packet_buffer import PacketBuffer


@pytest.mark.parametrize("text", ["=1+1", "+SUM(1)", "-SUM(1)", "@SUM(1)", "\t=1+1", "  =1+1"])
def test_csv_export_escapes_formula_cells_without_mutating_packet(text):
    buffer = PacketBuffer()
    packet = buffer.record("rx", text=text, sender_name=text, rssi=-70)
    row = next(csv.DictReader(io.StringIO(buffer.generate_csv())))
    assert row["Text_Message"].startswith("'")
    assert row["Sender_Name"].startswith("'")
    assert row["RSSI_dBm"] == "-70"
    assert packet.text == text
