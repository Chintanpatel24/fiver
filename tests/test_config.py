from pathlib import Path

from fiver.config import Config, load


def test_defaults():
    cfg = Config()
    assert cfg.adb_port == 5555
    assert cfg.prefer_wireless is True


def test_load_file(tmp_path: Path):
    p = tmp_path / "fiver.conf"
    p.write_text("BITRATE=4M\nMAX_SIZE=720\nPREFER_WIRELESS=false\nPHONE_IP=10.0.0.5\n")
    cfg = load(p)
    assert cfg.bitrate == "4M"
    assert cfg.max_size == 720
    assert cfg.prefer_wireless is False
    assert cfg.phone_ip == "10.0.0.5"
