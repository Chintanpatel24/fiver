import tempfile
import unittest
from pathlib import Path

from fiver.config import Config, load


class TestConfig(unittest.TestCase):
    def test_defaults(self):
        cfg = Config()
        self.assertEqual(cfg.adb_port, 5555)
        self.assertTrue(cfg.prefer_wireless)

    def test_load_file(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            p = Path(tmp_dir) / "fiver.conf"
            p.write_text("BITRATE=4M\nMAX_SIZE=720\nPREFER_WIRELESS=false\nPHONE_IP=10.0.0.5\n")
            cfg = load(p)
            self.assertEqual(cfg.bitrate, "4M")
            self.assertEqual(cfg.max_size, 720)
            self.assertFalse(cfg.prefer_wireless)
            self.assertEqual(cfg.phone_ip, "10.0.0.5")


if __name__ == "__main__":
    unittest.main()
