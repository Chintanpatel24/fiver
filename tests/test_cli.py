import unittest
from fiver.banner import render
from fiver.cli import build_parser, _merge_command


class TestCLI(unittest.TestCase):
    def test_banner_has_name(self):
        text = render("9.9.9")
        self.assertTrue("FIVER" in text or "██" in text)
        self.assertIn("9.9.9", text)

    def test_parser_start_flag(self):
        p = build_parser()
        args = p.parse_args(["--start", "--fg"])
        self.assertTrue(args.start)
        self.assertTrue(args.foreground)

    def test_parser_subcommand(self):
        p = build_parser()
        args = p.parse_args(["status"])
        self.assertEqual(args.command, "status")

    def test_parser_easy_flag(self):
        p = build_parser()
        args = p.parse_args(["--easy"])
        _merge_command(args)
        self.assertTrue(args.easy)

    def test_parser_easy_subcommand(self):
        p = build_parser()
        args = p.parse_args(["easy"])
        _merge_command(args)
        self.assertTrue(args.easy)

    def test_parser_update_flag(self):
        p = build_parser()
        args = p.parse_args(["--update"])
        _merge_command(args)
        self.assertTrue(args.update)

    def test_parser_update_subcommand(self):
        p = build_parser()
        args = p.parse_args(["update"])
        _merge_command(args)
        self.assertTrue(args.update)


if __name__ == "__main__":
    unittest.main()
