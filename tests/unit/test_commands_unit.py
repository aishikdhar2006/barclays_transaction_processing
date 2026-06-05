# Copyright (c) Meta Platforms, Inc. and affiliates.
#
# This source code is licensed under the BSD license found in the
# LICENSE file in the root directory of this source tree.

import argparse
from pathlib import Path
from unittest.mock import MagicMock, patch

import py.path
import pytest

from banking_tools import exceptions
from banking_tools.api_v4 import HTTPContentError
from banking_tools.commands import __main__ as cli_main
from banking_tools.commands.archive import Command as ArchiveCommand
from banking_tools.commands.authenticate import Command as AuthenticateCommand
from banking_tools.commands.batch_process import Command as BatchProcessCommand
from banking_tools.commands.batch_process_and_settle import (
    Command as BatchProcessAndSettleCommand,
)
from banking_tools.commands.process import Command as ProcessCommand, bold_text
from banking_tools.commands.process_and_settle import (
    Command as ProcessAndSettleCommand,
)
from banking_tools.commands.sample_transactions import (
    Command as SampleTransactionsCommand,
)
from banking_tools.commands.settle import Command as SettleCommand
from banking_tools.types import FileType


class TestBoldText:
    def test_returns_string(self):
        result = bold_text("hello")
        assert "hello" in result


class TestProcessCommand:
    def test_name_and_help(self):
        cmd = ProcessCommand()
        assert cmd.name == "process"
        assert cmd.help

    def test_add_basic_arguments(self):
        parser = argparse.ArgumentParser()
        cmd = ProcessCommand()
        cmd.add_basic_arguments(parser)
        args = parser.parse_args([])
        assert hasattr(args, "filetypes")

    @patch("banking_tools.commands.process.process_compliance_properties")
    @patch("banking_tools.commands.process.process_transaction_properties")
    @patch("banking_tools.commands.process.process_finalize")
    def test_run(self, mock_finalize, mock_txn, mock_geo):
        mock_geo.return_value = []
        mock_txn.return_value = []
        mock_finalize.return_value = []
        cmd = ProcessCommand()
        vars_args = {
            "import_path": Path("/tmp/test"),
            "filetypes": {FileType.IMAGE},
            "desc_path": None,
            "skip_subfolders": False,
        }
        cmd.run(vars_args)
        mock_geo.assert_called_once()
        mock_finalize.assert_called_once()
        assert "_metadatas_from_process" in vars_args


class TestSettleCommand:
    def test_name_and_help(self):
        cmd = SettleCommand()
        assert cmd.name == "settle"

    def test_add_basic_arguments(self):
        parser = argparse.ArgumentParser()
        cmd = SettleCommand()
        cmd.add_basic_arguments(parser)
        args = parser.parse_args([])
        assert hasattr(args, "desc_path")

    @patch("banking_tools.commands.settle.upload")
    @patch("banking_tools.commands.settle.fetch_user_items")
    def test_run_with_user_items(self, mock_fetch, mock_upload):
        cmd = SettleCommand()
        user_items = {"user_upload_token": "tok"}
        vars_args = {
            "user_items": user_items,
            "import_path": Path("/tmp"),
            "desc_path": None,
            "num_upload_workers": 1,
            "dry_run": True,
        }
        cmd.run(vars_args)
        mock_fetch.assert_not_called()
        mock_upload.assert_called_once()

    @patch("banking_tools.commands.settle.upload")
    @patch("banking_tools.commands.settle.fetch_user_items")
    def test_run_fetches_user_items(self, mock_fetch, mock_upload):
        mock_fetch.return_value = {"user_upload_token": "fetched"}
        cmd = SettleCommand()
        vars_args = {
            "import_path": Path("/tmp"),
            "desc_path": None,
            "num_upload_workers": 1,
            "dry_run": True,
        }
        cmd.run(vars_args)
        mock_fetch.assert_called_once()
        assert vars_args["user_items"]["user_upload_token"] == "fetched"


class TestSampleTransactionsCommand:
    def test_name(self):
        cmd = SampleTransactionsCommand()
        assert cmd.name == "sample_transactions"

    def test_add_basic_arguments(self):
        parser = argparse.ArgumentParser()
        cmd = SampleTransactionsCommand()
        cmd.add_basic_arguments(parser)

    @patch("banking_tools.commands.sample_transactions.sample_transactions")
    def test_run_with_dir(self, mock_sample, tmpdir: py.path.local):
        d = tmpdir.mkdir("videos")
        cmd = SampleTransactionsCommand()
        vars_args = {
            "video_import_path": Path(str(d)),
            "import_path": None,
        }
        cmd.run(vars_args)
        assert vars_args["import_path"] is not None
        mock_sample.assert_called_once()

    @patch("banking_tools.commands.sample_transactions.sample_transactions")
    def test_run_with_file(self, mock_sample, tmpdir: py.path.local):
        f = tmpdir.join("vid.mp4")
        f.write("x")
        cmd = SampleTransactionsCommand()
        vars_args = {
            "video_import_path": Path(str(f)),
            "import_path": None,
        }
        cmd.run(vars_args)
        assert vars_args["import_path"] is not None


class TestBatchProcessCommand:
    def test_name(self):
        cmd = BatchProcessCommand()
        assert cmd.name == "batch_process"

    @patch("banking_tools.commands.batch_process.ProcessCommand")
    @patch("banking_tools.commands.batch_process.SampleCommand")
    def test_run_forces_image_filetype(self, mock_sample_cls, mock_process_cls):
        mock_sample_inst = MagicMock()
        mock_process_inst = MagicMock()
        mock_sample_cls.return_value = mock_sample_inst
        mock_process_cls.return_value = mock_process_inst
        cmd = BatchProcessCommand()
        args = {"filetypes": {FileType.VIDEO}}
        cmd.run(args)
        assert args["filetypes"] == {FileType.IMAGE}
        mock_sample_inst.run.assert_called_once()
        mock_process_inst.run.assert_called_once()


class TestArchiveCommand:
    def test_name(self):
        cmd = ArchiveCommand()
        assert cmd.name == "archive"

    def test_add_basic_arguments(self):
        parser = argparse.ArgumentParser()
        cmd = ArchiveCommand()
        cmd.add_basic_arguments(parser)
        args = parser.parse_args(["/tmp/images", "/tmp/zips"])
        assert args.import_path == Path("/tmp/images")
        assert args.zip_dir == Path("/tmp/zips")

    @patch("banking_tools.commands.archive.zip_images")
    def test_run(self, mock_zip):
        cmd = ArchiveCommand()
        vars_args = {
            "import_path": Path("/tmp/images"),
            "zip_dir": Path("/tmp/zips"),
            "desc_path": None,
        }
        cmd.run(vars_args)
        mock_zip.assert_called_once()


class TestAuthenticateCommand:
    def test_name(self):
        cmd = AuthenticateCommand()
        assert cmd.name == "authenticate"

    def test_add_basic_arguments(self):
        parser = argparse.ArgumentParser()
        cmd = AuthenticateCommand()
        cmd.add_basic_arguments(parser)
        args = parser.parse_args(["--jwt", "my_token"])
        assert args.jwt == "my_token"


class TestProcessAndSettleCommand:
    def test_name(self):
        cmd = ProcessAndSettleCommand()
        assert cmd.name == "process_and_settle"

    @patch("banking_tools.commands.process_and_settle.ProcessCommand")
    @patch("banking_tools.commands.process_and_settle.UploadCommand")
    @patch("banking_tools.commands.process_and_settle.fetch_user_items")
    def test_run_sets_desc_path_and_fetches_user_items(
        self, mock_fetch, mock_upload_cls, mock_process_cls
    ):
        mock_fetch.return_value = {"user_upload_token": "tok"}
        mock_process_cls.return_value = MagicMock()
        mock_upload_cls.return_value = MagicMock()
        cmd = ProcessAndSettleCommand()
        vars_args = {"desc_path": None, "import_path": Path("/tmp")}
        cmd.run(vars_args)
        assert vars_args["desc_path"] == "\x00"
        mock_fetch.assert_called_once()


class TestBatchProcessAndSettleCommand:
    def test_name(self):
        cmd = BatchProcessAndSettleCommand()
        assert cmd.name == "batch_process_and_settle"

    @patch("banking_tools.commands.batch_process_and_settle.VideoProcessCommand")
    @patch("banking_tools.commands.batch_process_and_settle.UploadCommand")
    @patch("banking_tools.commands.batch_process_and_settle.fetch_user_items")
    def test_run_sets_desc_path(self, mock_fetch, mock_upload_cls, mock_video_cls):
        mock_fetch.return_value = {"user_upload_token": "tok"}
        mock_video_cls.return_value = MagicMock()
        mock_upload_cls.return_value = MagicMock()
        cmd = BatchProcessAndSettleCommand()
        vars_args = {"desc_path": None, "import_path": Path("/tmp")}
        cmd.run(vars_args)
        assert vars_args["desc_path"] == "\x00"


class TestMainFunction:
    @patch("banking_tools.commands.__main__.sys")
    def test_main_no_args_prints_help(self, mock_sys):
        mock_sys.argv = ["banking_tools"]
        mock_sys.exit = MagicMock(side_effect=SystemExit(0))
        with pytest.raises(SystemExit):
            cli_main.main()

    @patch("banking_tools.commands.__main__.sys")
    def test_main_help(self, mock_sys):
        mock_sys.argv = ["banking_tools", "--help"]
        mock_sys.exit = MagicMock(side_effect=SystemExit(0))
        with pytest.raises(SystemExit):
            cli_main.main()


class TestMainLogParams:
    def test_log_params(self, caplog):
        import logging

        with caplog.at_level(logging.DEBUG):
            cli_main._log_params({"key1": "val1", "key2": "val2"})


class TestMainAddGeneralArguments:
    def test_process_adds_import_path(self):
        parser = argparse.ArgumentParser()
        cli_main.add_general_arguments(parser, "process")
        args = parser.parse_args(["/tmp/path"])
        assert args.import_path == [Path("/tmp/path")]
        assert args.skip_subfolders is False

    def test_settle_adds_import_path(self):
        parser = argparse.ArgumentParser()
        cli_main.add_general_arguments(parser, "settle")
        args = parser.parse_args(["/tmp/a", "/tmp/b"])
        assert args.import_path == [Path("/tmp/a"), Path("/tmp/b")]

    def test_sample_transactions_adds_video_import_path(self):
        parser = argparse.ArgumentParser()
        cli_main.add_general_arguments(parser, "sample_transactions")
        args = parser.parse_args(["/tmp/video.mp4"])
        assert args.video_import_path == Path("/tmp/video.mp4")
