import pytest

from argparse import Namespace

from podcast_catcher.cli import build_parser, handle_add


def test_build_parser_has_expected_commands():
    parser = build_parser()
    subparsers_action = next(action for action in parser._actions if action.dest == "command")
    assert set(subparsers_action.choices) == {"add", "list", "download", "remove", "toggle", "refresh", "watch"}


def test_build_parser_accepts_priority_flag():
    parser = build_parser()
    args = parser.parse_args(["add", "https://example.com/feed.xml", "--priority"])
    assert args.priority is True


def test_build_parser_accepts_remove_command():
    parser = build_parser()
    args = parser.parse_args(["remove", "1"])
    assert args.feed_id == 1


def test_build_parser_accepts_toggle_command():
    parser = build_parser()
    args = parser.parse_args(["toggle", "1"])
    assert args.feed_id == 1


def test_build_parser_accepts_refresh_command():
    parser = build_parser()
    args = parser.parse_args(["refresh", "1"])
    assert args.feed_id == 1


def test_build_parser_refresh_allows_no_arguments():
    parser = build_parser()
    args = parser.parse_args(["refresh"])
    assert args.feed_id is None


def test_build_parser_watch_accepts_interval_and_once():
    parser = build_parser()
    args = parser.parse_args(["watch", "--interval", "60", "--once"])
    assert args.interval == 60
    assert args.once is True


def test_build_parser_download_accepts_count_option():
    parser = build_parser()
    args = parser.parse_args(["download", "--count", "5"])
    assert args.count == 5


def test_build_parser_download_count_defaults_to_3():
    parser = build_parser()
    args = parser.parse_args(["download"])
    assert args.count == 3


def test_build_parser_allows_help_for_each_command():
    parser = build_parser()
    for command in ("add", "list", "download", "remove", "toggle", "refresh", "watch"):
        with pytest.raises(SystemExit):
            parser.parse_args([command, "--help"])


@pytest.mark.parametrize("help_arg", ["help", "-help", "--help"])
def test_main_accepts_all_top_level_help_spellings(help_arg, capsys):
    from podcast_catcher.cli import main

    with pytest.raises(SystemExit) as error:
        main([help_arg])

    assert error.value.code == 0
    assert "usage: podcast-catcher" in capsys.readouterr().out


def test_handle_add_reports_invalid_url_without_traceback(monkeypatch, capsys):
    monkeypatch.setattr("podcast_catcher.cli.ensure_storage", lambda: object())

    result = handle_add(Namespace(url="example.com/feed.xml", name=None, priority=False))

    assert result == 1
    assert "Could not add feed: feed URL must be an absolute HTTP or HTTPS URL" in capsys.readouterr().out
