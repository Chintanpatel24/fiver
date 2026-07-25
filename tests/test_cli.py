from fiver.banner import render
from fiver.cli import build_parser


def test_banner_has_name():
    text = render("9.9.9")
    assert "FIVER" in text or "██" in text
    assert "9.9.9" in text


def test_parser_start_flag():
    p = build_parser()
    args = p.parse_args(["--start", "--fg"])
    assert args.start is True
    assert args.foreground is True


def test_parser_subcommand():
    p = build_parser()
    args = p.parse_args(["status"])
    assert args.command == "status"
