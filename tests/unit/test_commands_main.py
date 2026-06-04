# Copyright (c) Meta Platforms, Inc. and affiliates.
#
# This source code is licensed under the BSD license found in the
# LICENSE file in the root directory of this source tree.

import argparse
import enum
import logging
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests

from banking_tools import api_v4, exceptions
from banking_tools.commands.__main__ import (
    _log_params,
    add_general_arguments,
    main,
)


class TestLogParams:
    def test_skips_none_values(self, caplog):
        with caplog.at_level(logging.DEBUG, logger="banking_tools"):
            _log_params({"key": None})
        assert "key" not in caplog.text

    def test_skips_callables(self, caplog):
        with caplog.at_level(logging.DEBUG, logger="banking_tools"):
            _log_params({"func": lambda x: x})
        assert "func" not in caplog.text

    def test_redacts_jwt(self, caplog):
        with caplog.at_level(logging.DEBUG, logger="banking_tools"):
            _log_params({"jwt": "secret_token_value"})
        assert "secret_token_value" not in caplog.text
        assert "******" in caplog.text

    def test_redacts_user_password(self, caplog):
        with caplog.at_level(logging.DEBUG, logger="banking_tools"):
            _log_params({"user_password": "mypassword"})
        assert "mypassword" not in caplog.text
        assert "******" in caplog.text

    def test_logs_string_value(self, caplog):
        with caplog.at_level(logging.DEBUG, logger="banking_tools"):
            _log_params({"import_path": "/tmp/data"})
        assert "/tmp/data" in caplog.text

    def test_logs_short_list(self, caplog):
        with caplog.at_level(logging.DEBUG, logger="banking_tools"):
            _log_params({"paths": [Path("/a"), Path("/b")]})
        assert str(Path("/a")) in caplog.text
        assert str(Path("/b")) in caplog.text

    def test_logs_long_list_truncated(self, caplog):
        with caplog.at_level(logging.DEBUG, logger="banking_tools"):
            items = [f"item{i}" for i in range(10)]
            _log_params({"items": items})
        assert "and 5 more" in caplog.text

    def test_logs_enum_value(self, caplog):
        class Color(enum.Enum):
            RED = "red"

        with caplog.at_level(logging.DEBUG, logger="banking_tools"):
            _log_params({"color": Color.RED})
        assert "red" in caplog.text


class TestAddGeneralArguments:
    def test_process_command_args(self):
        parser = argparse.ArgumentParser()
        add_general_arguments(parser, "process")
        args = parser.parse_args(["/tmp/data"])
        assert args.import_path == [Path("/tmp/data")]
        assert args.skip_subfolders is False

    def test_settle_command_args(self):
        parser = argparse.ArgumentParser()
        add_general_arguments(parser, "settle")
        args = parser.parse_args(["/tmp/data"])
        assert args.import_path == [Path("/tmp/data")]

    def test_sample_transactions_command_args(self):
        parser = argparse.ArgumentParser()
        add_general_arguments(parser, "sample_transactions")
        args = parser.parse_args(["/tmp/video"])
        assert args.video_import_path == Path("/tmp/video")

    def test_batch_process_command_args(self):
        parser = argparse.ArgumentParser()
        add_general_arguments(parser, "batch_process")
        args = parser.parse_args(["/tmp/video", "/tmp/output"])
        assert args.video_import_path == Path("/tmp/video")
        assert args.import_path == Path("/tmp/output")

    def test_process_and_settle_command_args(self):
        parser = argparse.ArgumentParser()
        add_general_arguments(parser, "process_and_settle")
        args = parser.parse_args(["--skip_subfolders", "/tmp/data"])
        assert args.skip_subfolders is True


class TestMain:
    @patch("sys.argv", ["banking_tools", "--version"])
    def test_version(self):
        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 0

    @patch("sys.argv", ["banking_tools"])
    @patch("argparse.ArgumentParser.print_help")
    def test_no_args_prints_help(self, mock_help):
        main()
        mock_help.assert_called_once()

    @patch("sys.argv", ["banking_tools", "--verbose", "process", "/tmp/data"])
    @patch("banking_tools.commands.process.Command.run")
    def test_process_command(self, mock_run):
        main()
        mock_run.assert_called_once()

    @patch("sys.argv", ["banking_tools", "process", "/tmp/data"])
    @patch("banking_tools.commands.process.Command.run")
    def test_process_http_error_exits_16(self, mock_run):
        resp = MagicMock(spec=requests.Response)
        resp.status_code = 500
        resp.reason = "Server Error"
        resp.url = "http://api.example.com"
        resp.content = b"error"
        resp.request = MagicMock()
        resp.request.method = "POST"
        resp.json.side_effect = requests.JSONDecodeError("", "", 0)
        mock_run.side_effect = requests.HTTPError(response=resp)

        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 16

    @patch("sys.argv", ["banking_tools", "process", "/tmp/data"])
    @patch("banking_tools.commands.process.Command.run")
    def test_process_http_content_error_exits_17(self, mock_run):
        resp = MagicMock(spec=requests.Response)
        resp.status_code = 400
        resp.reason = "Bad Request"
        resp.url = "http://api.example.com"
        resp.content = b"bad"
        resp.request = MagicMock()
        resp.request.method = "POST"
        resp.json.side_effect = requests.JSONDecodeError("", "", 0)
        mock_run.side_effect = api_v4.HTTPContentError("bad content", response=resp)

        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 17

    @patch("sys.argv", ["banking_tools", "process", "/tmp/data"])
    @patch("banking_tools.commands.process.Command.run")
    def test_process_user_error_exits_with_code(self, mock_run):
        mock_run.side_effect = exceptions.BankingPlatformBadParameterError("bad param")

        with pytest.raises(SystemExit) as exc_info:
            main()
        # BankingPlatformBadParameterError has a specific exit code
        assert exc_info.value.code != 0

    @patch("sys.argv", ["banking_tools", "process", "/tmp/data"])
    @patch("banking_tools.commands.process.Command.run")
    def test_keyboard_interrupt(self, mock_run):
        mock_run.side_effect = KeyboardInterrupt()
        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 130
