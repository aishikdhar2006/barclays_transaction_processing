# Copyright (c) Meta Platforms, Inc. and affiliates.
#
# This source code is licensed under the BSD license found in the
# LICENSE file in the root directory of this source tree.

import argparse
from pathlib import Path
from unittest.mock import MagicMock, patch


from banking_tools.commands import (
    archive,
    authenticate,
    batch_process,
    batch_process_and_settle,
    process,
    process_and_settle,
    sample_transactions,
    settle,
)
from banking_tools import types


class TestProcessCommand:
    def test_name_and_help(self):
        cmd = process.Command()
        assert cmd.name == "process"
        assert cmd.help is not None

    def test_add_basic_arguments(self):
        cmd = process.Command()
        parser = argparse.ArgumentParser()
        parser.add_argument("import_path", nargs="+", type=Path)
        cmd.add_basic_arguments(parser)
        # Verify key args exist
        args = parser.parse_args(["/tmp/data", "--desc_path", "/tmp/desc.json"])
        assert args.desc_path == "/tmp/desc.json"

    @patch("banking_tools.commands.process.process_compliance_properties")
    @patch("banking_tools.commands.process.process_transaction_properties")
    @patch("banking_tools.commands.process.process_finalize")
    def test_run(self, mock_finalize, mock_txn, mock_compliance):
        cmd = process.Command()
        mock_compliance.return_value = []
        mock_txn.return_value = []
        mock_finalize.return_value = None

        vars_args = {
            "import_path": [Path("/tmp/data")],
            "skip_subfolders": False,
            "desc_path": None,
            "geotag_source": [],
            "geotag_source_path": None,
            "video_geotag_source": None,
            "video_geotag_source_path": None,
            "interpolation_offset_time": 0.0,
            "interpolation_use_gpx_start_time": False,
            "overwrite_all_EXIF_tags": False,
            "overwrite_EXIF_time_tag": False,
            "overwrite_EXIF_gps_tag": False,
            "overwrite_EXIF_direction_tag": False,
            "overwrite_EXIF_orientation_tag": False,
            "device_make": None,
            "device_model": None,
            "filetypes": None,
            "skip_process_errors": False,
            "num_processes": None,
        }
        cmd.run(vars_args)
        mock_compliance.assert_called_once()


class TestSettleCommand:
    def test_name_and_help(self):
        cmd = settle.Command()
        assert cmd.name == "settle"
        assert cmd.help is not None

    def test_add_basic_arguments(self):
        cmd = settle.Command()
        parser = argparse.ArgumentParser()
        parser.add_argument("import_path", nargs="+", type=Path)
        cmd.add_basic_arguments(parser)
        args = parser.parse_args(["/tmp/data", "--dry_run"])
        assert args.dry_run is True

    @patch("banking_tools.commands.settle.fetch_user_items")
    @patch("banking_tools.commands.settle.upload")
    def test_run(self, mock_upload, mock_fetch):
        cmd = settle.Command()
        mock_fetch.return_value = {"user_upload_token": "tok"}

        vars_args = {
            "import_path": [Path("/tmp/data")],
            "user_name": None,
            "organization_key": None,
            "num_upload_workers": 4,
            "reupload": False,
            "dry_run": True,
            "nofinish": False,
            "noresume": False,
            "desc_path": None,
            "skip_subfolders": False,
        }
        cmd.run(vars_args)
        mock_fetch.assert_called_once()
        mock_upload.assert_called_once()


class TestAuthenticateCommand:
    def test_name_and_help(self):
        cmd = authenticate.Command()
        assert cmd.name == "authenticate"
        assert cmd.help is not None

    def test_add_basic_arguments(self):
        cmd = authenticate.Command()
        parser = argparse.ArgumentParser()
        cmd.add_basic_arguments(parser)
        args = parser.parse_args(["--user_name", "myuser", "--jwt", "token"])
        assert args.user_name == "myuser"
        assert args.jwt == "token"

    @patch("banking_tools.commands.authenticate.authenticate")
    def test_run(self, mock_auth):
        cmd = authenticate.Command()
        vars_args = {
            "user_name": "testuser",
            "user_email": None,
            "user_password": None,
            "jwt": "my_token",
            "delete": False,
        }
        cmd.run(vars_args)
        mock_auth.assert_called_once()


class TestArchiveCommand:
    def test_name_and_help(self):
        cmd = archive.Command()
        assert cmd.name == "archive"
        assert cmd.help is not None

    def test_add_basic_arguments(self):
        cmd = archive.Command()
        parser = argparse.ArgumentParser()
        cmd.add_basic_arguments(parser)
        args = parser.parse_args(["/tmp/images", "/tmp/zips"])
        assert args.import_path == Path("/tmp/images")
        assert args.zip_dir == Path("/tmp/zips")

    @patch("banking_tools.commands.archive.zip_images")
    def test_run(self, mock_zip):
        cmd = archive.Command()
        vars_args = {
            "import_path": Path("/tmp/images"),
            "zip_dir": Path("/tmp/zips"),
            "desc_path": None,
        }
        cmd.run(vars_args)
        mock_zip.assert_called_once()


class TestSampleTransactionsCommand:
    def test_name_and_help(self):
        cmd = sample_transactions.Command()
        assert cmd.name == "sample_transactions"
        assert cmd.help is not None

    def test_add_basic_arguments(self):
        cmd = sample_transactions.Command()
        parser = argparse.ArgumentParser()
        parser.add_argument("video_import_path", type=Path)
        parser.add_argument("import_path", nargs="?", type=Path)
        cmd.add_basic_arguments(parser)
        args = parser.parse_args(["/tmp/video", "--video_sample_distance", "5.0"])
        assert args.video_sample_distance == 5.0

    @patch("banking_tools.commands.sample_transactions.sample_transactions")
    def test_run_with_dir(self, mock_sample, tmp_path):
        cmd = sample_transactions.Command()
        video_dir = tmp_path / "videos"
        video_dir.mkdir()
        vars_args = {
            "video_import_path": video_dir,
            "import_path": None,
            "video_sample_distance": 3.0,
            "video_sample_interval": 2.0,
            "video_duration_ratio": 1.0,
            "video_start_time": None,
            "skip_subfolders": False,
            "rerun": False,
            "skip_sample_errors": False,
        }
        cmd.run(vars_args)
        mock_sample.assert_called_once()
        # Verify import_path was set to default
        assert vars_args["import_path"] is not None

    @patch("banking_tools.commands.sample_transactions.sample_transactions")
    def test_run_with_file(self, mock_sample, tmp_path):
        cmd = sample_transactions.Command()
        video_file = tmp_path / "test.mp4"
        video_file.touch()
        vars_args = {
            "video_import_path": video_file,
            "import_path": None,
            "video_sample_distance": 3.0,
            "video_sample_interval": 2.0,
            "video_duration_ratio": 1.0,
            "video_start_time": None,
            "skip_subfolders": False,
            "rerun": False,
            "skip_sample_errors": False,
        }
        cmd.run(vars_args)
        assert vars_args["import_path"] is not None


class TestBatchProcessCommand:
    def test_name_and_help(self):
        cmd = batch_process.Command()
        assert cmd.name == "batch_process"
        assert cmd.help is not None

    @patch("banking_tools.commands.batch_process.SampleCommand")
    @patch("banking_tools.commands.batch_process.ProcessCommand")
    def test_run_forces_filetypes(self, mock_process_cls, mock_sample_cls):
        mock_sample = MagicMock()
        mock_sample_cls.return_value = mock_sample
        mock_process = MagicMock()
        mock_process_cls.return_value = mock_process

        cmd = batch_process.Command()
        args = {"filetypes": {types.FileType.VIDEO}}
        cmd.run(args)
        # Verify filetypes was forced to IMAGE
        assert args["filetypes"] == {types.FileType.IMAGE}
        mock_sample.run.assert_called_once()
        mock_process.run.assert_called_once()


class TestProcessAndSettleCommand:
    def test_name_and_help(self):
        cmd = process_and_settle.Command()
        assert cmd.name == "process_and_settle"
        assert cmd.help is not None

    @patch("banking_tools.commands.process_and_settle.fetch_user_items")
    @patch("banking_tools.commands.process_and_settle.ProcessCommand")
    @patch("banking_tools.commands.process_and_settle.UploadCommand")
    def test_run(self, mock_upload_cls, mock_process_cls, mock_fetch):
        mock_fetch.return_value = {"user_upload_token": "tok"}
        mock_process = MagicMock()
        mock_process_cls.return_value = mock_process
        mock_upload = MagicMock()
        mock_upload_cls.return_value = mock_upload

        cmd = process_and_settle.Command()
        vars_args = {
            "desc_path": None,
            "user_name": None,
            "organization_key": None,
        }
        cmd.run(vars_args)
        # desc_path should be set to null byte
        assert vars_args["desc_path"] == "\x00"
        mock_fetch.assert_called_once()
        mock_process.run.assert_called_once()
        mock_upload.run.assert_called_once()


class TestBatchProcessAndSettleCommand:
    def test_name_and_help(self):
        cmd = batch_process_and_settle.Command()
        assert cmd.name == "batch_process_and_settle"
        assert cmd.help is not None
