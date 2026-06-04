# Copyright (c) Meta Platforms, Inc. and affiliates.
#
# This source code is licensed under the BSD license found in the
# LICENSE file in the root directory of this source tree.

import logging
import time
import typing as T
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests

from banking_tools import (
    api_v4,
    constants,
    exceptions,
    processor,
    settlement,
    types,
)


class TestNormalizeImportPaths:
    def test_single_path(self, tmp_path):
        d = tmp_path / "data"
        d.mkdir()
        result = settlement._normalize_import_paths(d)
        assert result == [d]

    def test_list_of_paths(self, tmp_path):
        d1 = tmp_path / "data1"
        d2 = tmp_path / "data2"
        d1.mkdir()
        d2.mkdir()
        result = settlement._normalize_import_paths([d1, d2])
        assert d1 in result
        assert d2 in result

    def test_deduplicates_paths(self, tmp_path):
        d = tmp_path / "data"
        d.mkdir()
        result = settlement._normalize_import_paths([d, d])
        assert len(result) == 1

    def test_nonexistent_path_raises(self, tmp_path):
        nonexistent = tmp_path / "nonexistent"
        with pytest.raises(exceptions.BankingPlatformFileNotFoundError):
            settlement._normalize_import_paths(nonexistent)

    def test_file_path(self, tmp_path):
        f = tmp_path / "file.jpg"
        f.touch()
        result = settlement._normalize_import_paths(f)
        assert result == [f]


class TestContinueOrFail:
    def test_sequence_error_returns(self):
        err = processor.SequenceError("test")
        result = settlement._continue_or_fail(err)
        assert result is err

    def test_file_not_found_returns(self):
        err = FileNotFoundError("missing")
        result = settlement._continue_or_fail(err)
        assert result is err

    def test_permission_error_returns(self):
        err = PermissionError("denied")
        result = settlement._continue_or_fail(err)
        assert result is err

    def test_metadata_validation_error_returns(self):
        err = exceptions.BankingPlatformMetadataValidationError("bad")
        result = settlement._continue_or_fail(err)
        assert result is err

    def test_connection_error_raises_upload_connection_error(self):
        err = requests.ConnectionError("conn err")
        with pytest.raises(exceptions.BankingPlatformUploadConnectionError):
            settlement._continue_or_fail(err)

    def test_timeout_raises_upload_timeout_error(self):
        err = requests.Timeout("timeout")
        with pytest.raises(exceptions.BankingPlatformUploadTimeoutError):
            settlement._continue_or_fail(err)

    def test_http_auth_error_raises_unauthorized(self):
        resp = MagicMock(spec=requests.Response)
        resp.status_code = 401
        resp.json.return_value = {"error": {"message": "auth fail"}}
        err = requests.HTTPError(response=resp)
        with patch.object(api_v4, "is_auth_error", return_value=True):
            with patch.object(
                api_v4, "extract_auth_error_message", return_value="auth fail"
            ):
                with pytest.raises(exceptions.BankingPlatformUploadUnauthorizedError):
                    settlement._continue_or_fail(err)

    def test_http_non_auth_error_reraises(self):
        resp = MagicMock(spec=requests.Response)
        resp.status_code = 500
        err = requests.HTTPError(response=resp)
        with patch.object(api_v4, "is_auth_error", return_value=False):
            with pytest.raises(requests.HTTPError):
                settlement._continue_or_fail(err)

    def test_generic_exception_reraises(self):
        err = RuntimeError("unexpected")
        with pytest.raises(RuntimeError):
            settlement._continue_or_fail(err)


class TestIsHistoryDisabled:
    def test_disabled_when_no_history_path(self):
        with patch.object(constants, "MAPILLARY_UPLOAD_HISTORY_PATH", ""):
            assert settlement._is_history_disabled(dry_run=False) is True

    def test_disabled_when_dry_run_without_enable(self):
        with patch.object(constants, "MAPILLARY_UPLOAD_HISTORY_PATH", "/tmp/hist"):
            with patch.object(
                constants, "MAPILLARY__ENABLE_UPLOAD_HISTORY_FOR_DRY_RUN", False
            ):
                assert settlement._is_history_disabled(dry_run=True) is True

    def test_enabled_when_dry_run_with_enable(self):
        with patch.object(constants, "MAPILLARY_UPLOAD_HISTORY_PATH", "/tmp/hist"):
            with patch.object(
                constants, "MAPILLARY__ENABLE_UPLOAD_HISTORY_FOR_DRY_RUN", True
            ):
                assert settlement._is_history_disabled(dry_run=True) is False

    def test_enabled_when_not_dry_run(self):
        with patch.object(constants, "MAPILLARY_UPLOAD_HISTORY_PATH", "/tmp/hist"):
            assert settlement._is_history_disabled(dry_run=False) is False


class TestLogException:
    def test_log_uploaded_already(self, caplog):
        ex = settlement.UploadedAlready("already uploaded")
        with caplog.at_level(logging.INFO):
            settlement.log_exception(ex)
        assert "already uploaded" in caplog.text

    def test_log_http_error(self, caplog):
        resp = MagicMock(spec=requests.Response)
        resp.status_code = 500
        resp.reason = "Server Error"
        resp.url = "http://example.com"
        resp.content = b"error"
        resp.request = MagicMock()
        resp.request.method = "POST"
        resp.json.side_effect = requests.JSONDecodeError("", "", 0)
        ex = requests.HTTPError(response=resp)
        with caplog.at_level(logging.ERROR):
            settlement.log_exception(ex)
        assert "HTTPError" in caplog.text

    def test_log_http_content_error(self, caplog):
        resp = MagicMock(spec=requests.Response)
        resp.status_code = 400
        resp.reason = "Bad Request"
        resp.url = "http://example.com"
        resp.content = b"bad"
        resp.request = MagicMock()
        resp.request.method = "POST"
        resp.json.side_effect = requests.JSONDecodeError("", "", 0)
        ex = api_v4.HTTPContentError("content error", response=resp)
        with caplog.at_level(logging.ERROR):
            settlement.log_exception(ex)
        assert "HTTPContentError" in caplog.text

    def test_log_generic_error(self, caplog):
        ex = RuntimeError("something broke")
        with caplog.at_level(logging.ERROR):
            settlement.log_exception(ex)
        assert "something broke" in caplog.text


class TestSummarize:
    def test_empty_stats(self):
        result = settlement._summarize([])
        assert result["images"] == 0
        assert result["sequences"] == 0
        assert result["size"] == 0
        assert result["uploaded_size"] == 0
        assert result["speed"] == 0
        assert result["time"] == 0

    def test_single_stat(self):
        stats = [
            {
                "sequence_image_count": 10,
                "entity_size": 1024 * 1024,  # 1MB
                "upload_first_offset": 0,
                "upload_total_time": 2.0,
            }
        ]
        result = settlement._summarize(stats)
        assert result["images"] == 10
        assert result["sequences"] == 1
        assert result["size"] == 1.0
        assert result["uploaded_size"] == 1.0
        assert result["time"] == 2.0
        assert result["speed"] == 0.5

    def test_multiple_stats(self):
        stats = [
            {
                "sequence_image_count": 5,
                "entity_size": 2 * 1024 * 1024,
                "upload_first_offset": 1024 * 1024,
                "upload_total_time": 1.0,
            },
            {
                "sequence_image_count": 3,
                "entity_size": 1024 * 1024,
                "upload_first_offset": 0,
                "upload_total_time": 1.0,
            },
        ]
        result = settlement._summarize(stats)
        assert result["images"] == 8
        assert result["sequences"] == 2
        assert result["time"] == 2.0


class TestShowUploadSummary:
    def test_no_stats_no_errors(self, caplog):
        with caplog.at_level(logging.INFO):
            settlement._show_upload_summary([], [])
        assert "Nothing uploaded" in caplog.text

    def test_with_stats(self, caplog):
        stats = [
            {
                "sequence_image_count": 5,
                "entity_size": 1024 * 1024,
                "upload_first_offset": 0,
                "upload_total_time": 1.0,
                "file_type": "image",
            }
        ]
        with caplog.at_level(logging.INFO):
            settlement._show_upload_summary(stats, [])
        assert "1 sequences uploaded" in caplog.text

    def test_with_uploaded_already_errors(self, caplog):
        errors = [
            settlement.UploadedAlready("dup1"),
            settlement.UploadedAlready("dup2"),
        ]
        with caplog.at_level(logging.INFO):
            settlement._show_upload_summary([], errors)
        assert "Skipped 2 already uploaded" in caplog.text

    def test_with_generic_errors(self, caplog):
        errors = [RuntimeError("err1")]
        with caplog.at_level(logging.INFO):
            settlement._show_upload_summary([], errors)
        assert "1 uploads failed" in caplog.text


class TestApiLogging:
    def test_api_logging_finished_dry_run_skips(self):
        # Should not raise
        settlement._api_logging_finished({}, dry_run=True)

    def test_api_logging_finished_disabled(self):
        with patch.object(constants, "MAPILLARY_DISABLE_API_LOGGING", True):
            settlement._api_logging_finished({}, dry_run=False)

    @patch("banking_tools.api_v4.create_client_session")
    @patch("banking_tools.api_v4.log_event")
    def test_api_logging_finished_success(self, mock_log_event, mock_session):
        mock_session.return_value.__enter__ = MagicMock()
        mock_session.return_value.__exit__ = MagicMock(return_value=False)
        with patch.object(constants, "MAPILLARY_DISABLE_API_LOGGING", False):
            settlement._api_logging_finished({"images": 5}, dry_run=False)

    def test_api_logging_failed_dry_run_skips(self):
        settlement._api_logging_failed({}, RuntimeError("x"), dry_run=True)

    def test_api_logging_failed_disabled(self):
        with patch.object(constants, "MAPILLARY_DISABLE_API_LOGGING", True):
            settlement._api_logging_failed({}, RuntimeError("x"), dry_run=False)


class TestZipImages:
    def test_nonexistent_import_path(self, tmp_path):
        with pytest.raises(exceptions.BankingPlatformFileNotFoundError):
            settlement.zip_images(tmp_path / "nonexistent", tmp_path / "zips")

    @patch("banking_tools.settlement._load_valid_metadatas_from_desc_path")
    def test_no_metadatas_found(self, mock_load, tmp_path, caplog):
        mock_load.return_value = []
        d = tmp_path / "data"
        d.mkdir()
        with caplog.at_level(logging.WARNING):
            settlement.zip_images(d, tmp_path / "zips")
        assert "No images" in caplog.text


class TestSetupApiStats:
    def test_collects_start_and_end_times(self):
        emitter = processor.EventEmitter()
        settlement._setup_api_stats(emitter)

        payload: T.Dict[str, T.Any] = {
            "entity_size": 1024,
            "offset": 0,
        }
        # Mock time so elapsed is deterministic across platforms (Windows
        # time.time() resolution is too coarse for instantaneous emits).
        with patch.object(settlement.time, "time", side_effect=[100.0, 105.0]):
            emitter.emit("upload_start", payload)
            assert "upload_start_time" in payload
            assert "upload_total_time" in payload

            emitter.emit("upload_end", payload)
        assert "upload_end_time" in payload
        assert payload["upload_total_time"] == 5.0

    def test_collects_fetch_offset(self):
        emitter = processor.EventEmitter()
        settlement._setup_api_stats(emitter)

        payload: T.Dict[str, T.Any] = {
            "entity_size": 1024,
            "offset": 512,
        }
        emitter.emit("upload_start", payload)
        emitter.emit("upload_fetch_offset", payload)
        assert payload["upload_first_offset"] == 0  # min(512, 0) = 0

    def test_retrying_accumulates_time(self):
        emitter = processor.EventEmitter()
        settlement._setup_api_stats(emitter)

        payload: T.Dict[str, T.Any] = {
            "entity_size": 1024,
            "offset": 0,
        }
        with patch.object(settlement.time, "time", side_effect=[100.0, 105.0]):
            emitter.emit("upload_start", payload)
            emitter.emit("upload_retrying", payload)
        assert payload["upload_total_time"] == 5.0
        assert "upload_last_restart_time" not in payload

    def test_finished_appends_to_stats(self):
        emitter = processor.EventEmitter()
        stats = settlement._setup_api_stats(emitter)

        payload: T.Dict[str, T.Any] = {
            "entity_size": 1024,
            "offset": 0,
        }
        emitter.emit("upload_start", payload)
        emitter.emit("upload_end", payload)
        emitter.emit("upload_finished", payload)
        assert len(stats) == 1


class TestSetupTdqm:
    def test_tqdm_events(self):
        emitter = processor.EventEmitter()
        settlement._setup_tdqm(emitter)

        payload = {
            "sequence_idx": 0,
            "total_sequence_count": 1,
            "entity_size": 1024,
            "file_type": "image",
            "import_path": "/tmp/test.jpg",
        }
        # Should not raise
        emitter.emit("upload_start", payload)
        emitter.emit("upload_progress", {"chunk_size": 512})
        emitter.emit("upload_end", {})

    def test_tqdm_without_import_path(self):
        emitter = processor.EventEmitter()
        settlement._setup_tdqm(emitter)

        payload = {
            "sequence_idx": 0,
            "total_sequence_count": 1,
            "entity_size": 1024,
            "file_type": "image",
        }
        emitter.emit("upload_start", payload)
        emitter.emit("upload_end", {})


class TestSetupIpc:
    @patch("banking_tools.ipc.send")
    def test_ipc_events(self, mock_send):
        emitter = processor.EventEmitter()
        settlement._setup_ipc(emitter)

        payload = {"sequence_idx": 0, "total_sequence_count": 1}
        emitter.emit("upload_start", payload)
        assert mock_send.called

    @patch("banking_tools.ipc.send")
    def test_ipc_upload_progress(self, mock_send):
        emitter = processor.EventEmitter()
        settlement._setup_ipc(emitter)

        payload = {"chunk_size": 512}
        emitter.emit("upload_progress", payload)
        mock_send.assert_called_with("upload_progress", payload)


class TestFindMetadataWithFilenameExistedIn:
    def test_finds_matching_metadata(self, tmp_path):
        f1 = tmp_path / "img1.jpg"
        f1.touch()
        f2 = tmp_path / "img2.jpg"
        f2.touch()

        m1 = MagicMock(spec=types.ImageMetadata)
        m1.filename = f1
        m2 = MagicMock(spec=types.ImageMetadata)
        m2.filename = f2

        result = settlement._find_metadata_with_filename_existed_in([m1, m2], [f1])
        assert len(result) == 1
        assert result[0] is m1

    def test_no_matches(self, tmp_path):
        f1 = tmp_path / "img1.jpg"
        f1.touch()
        f2 = tmp_path / "other.jpg"
        f2.touch()

        m1 = MagicMock(spec=types.ImageMetadata)
        m1.filename = f1

        result = settlement._find_metadata_with_filename_existed_in([m1], [f2])
        assert len(result) == 0


class TestUploadedAlready:
    def test_is_sequence_error(self):
        ex = settlement.UploadedAlready("test")
        assert isinstance(ex, processor.SequenceError)


class TestSetupHistory:
    @patch(
        "banking_tools.settlement.constants.MAPILLARY_UPLOAD_HISTORY_PATH", "/tmp/hist"
    )
    def test_check_duplication_raises_uploaded_already(self):
        emitter = processor.EventEmitter()
        settlement._setup_history(
            emitter,
            upload_run_params={},
            metadatas=[],
            reupload=False,
            nofinish=False,
        )
        # Simulate an already-uploaded record
        with patch("banking_tools.settlement.history.read_history_record") as mock_read:
            mock_read.return_value = {"summary": {"upload_end_time": time.time() - 100}}
            payload = {"sequence_md5sum": "abc123", "import_path": "/tmp/test.jpg"}
            with pytest.raises(settlement.UploadedAlready):
                emitter.emit("upload_start", payload)

    @patch(
        "banking_tools.settlement.constants.MAPILLARY_UPLOAD_HISTORY_PATH", "/tmp/hist"
    )
    def test_reupload_does_not_raise(self):
        emitter = processor.EventEmitter()
        settlement._setup_history(
            emitter,
            upload_run_params={},
            metadatas=[],
            reupload=True,
            nofinish=False,
        )
        with patch("banking_tools.settlement.history.read_history_record") as mock_read:
            mock_read.return_value = {"summary": {"upload_end_time": time.time() - 100}}
            payload = {"sequence_md5sum": "abc123", "import_path": "/tmp/test.jpg"}
            # Should not raise
            emitter.emit("upload_start", payload)

    @patch(
        "banking_tools.settlement.constants.MAPILLARY_UPLOAD_HISTORY_PATH", "/tmp/hist"
    )
    def test_no_record_does_not_raise(self):
        emitter = processor.EventEmitter()
        settlement._setup_history(
            emitter,
            upload_run_params={},
            metadatas=[],
            reupload=False,
            nofinish=False,
        )
        with patch("banking_tools.settlement.history.read_history_record") as mock_read:
            mock_read.return_value = None
            payload = {"sequence_md5sum": "abc123"}
            # Should not raise when no record exists
            emitter.emit("upload_start", payload)

    @patch(
        "banking_tools.settlement.constants.MAPILLARY_UPLOAD_HISTORY_PATH", "/tmp/hist"
    )
    def test_write_history_on_finish(self):
        emitter = processor.EventEmitter()
        settlement._setup_history(
            emitter,
            upload_run_params={"desc_path": "/tmp"},
            metadatas=[],
            reupload=False,
            nofinish=False,
        )
        with patch("banking_tools.settlement.history.write_history") as mock_write:
            payload = {"sequence_md5sum": "abc123", "sequence_uuid": None}
            emitter.emit("upload_finished", payload)
            mock_write.assert_called_once()

    @patch(
        "banking_tools.settlement.constants.MAPILLARY_UPLOAD_HISTORY_PATH", "/tmp/hist"
    )
    def test_nofinish_skips_write_history(self):
        emitter = processor.EventEmitter()
        settlement._setup_history(
            emitter,
            upload_run_params={},
            metadatas=[],
            reupload=False,
            nofinish=True,
        )
        with patch("banking_tools.settlement.history.write_history") as mock_write:
            payload = {"sequence_md5sum": "abc123", "sequence_uuid": None}
            emitter.emit("upload_finished", payload)
            mock_write.assert_not_called()


class TestSetupApiStatsExtended:
    def test_collects_start_time(self):
        emitter = processor.EventEmitter()
        settlement._setup_api_stats(emitter)

        payload: T.Any = {
            "sequence_md5sum": "test",
            "file_type": "image",
            "total_sequence_count": 1,
            "sequence_idx": 0,
            "chunk_size": 0,
            "begin_offset": None,
            "offset": 0,
            "entity_size": 1024,
            "retries": 0,
            "cluster_id": "",
        }
        emitter.emit("upload_start", payload)
        assert "upload_start_time" in payload
        assert "upload_total_time" in payload

    def test_collects_end_time(self):
        emitter = processor.EventEmitter()
        settlement._setup_api_stats(emitter)

        payload: T.Any = {
            "sequence_md5sum": "test",
            "file_type": "image",
            "total_sequence_count": 1,
            "sequence_idx": 0,
            "chunk_size": 0,
            "begin_offset": None,
            "offset": 0,
            "entity_size": 1024,
            "retries": 0,
            "cluster_id": "",
            "upload_last_restart_time": time.time(),
            "upload_total_time": 0,
        }
        emitter.emit("upload_end", payload)
        assert "upload_end_time" in payload

    def test_finished_appends_stats(self):
        emitter = processor.EventEmitter()
        stats = settlement._setup_api_stats(emitter)

        payload: T.Any = {
            "sequence_md5sum": "test",
            "file_type": "image",
            "total_sequence_count": 1,
            "sequence_idx": 0,
        }
        emitter.emit("upload_finished", payload)
        assert len(stats) == 1

    def test_retrying_accumulates_time(self):
        emitter = processor.EventEmitter()
        settlement._setup_api_stats(emitter)

        payload: T.Any = {
            "upload_last_restart_time": 100.0,
            "upload_total_time": 0,
        }
        with patch.object(settlement.time, "time", return_value=105.0):
            emitter.emit("upload_retrying", payload)
        assert payload["upload_total_time"] == 5.0
        assert "upload_last_restart_time" not in payload


class TestLoadDescs:
    def test_from_process_metadatas(self, tmp_path):
        img = tmp_path / "test.jpg"
        img.touch()
        metadata = types.ImageMetadata(
            filename=img,
            lat=40.0,
            lon=-74.0,
            alt=None,
            angle=None,
            time=100.0,
            MAPOrientation=1,
        )
        result = settlement._load_descs([metadata], [tmp_path], None)
        assert len(result) == 1
        # Should assign sequence UUID
        assert result[0].MAPSequenceUUID is not None

    def test_error_metadata_filtered_out(self, tmp_path):
        img = tmp_path / "test.jpg"
        img.touch()
        error_metadata = types.ErrorMetadata(
            filename=img,
            filetype=types.FileType.IMAGE,
            error=exceptions.BankingPlatformGeoTaggingError("no gps"),
        )
        result = settlement._load_descs([error_metadata], [tmp_path], None)
        assert len(result) == 0


class TestContinueOrFailExtended:
    def test_connection_error_raises_upload_connection_error(self):
        ex = requests.ConnectionError("connection refused")
        with pytest.raises(exceptions.BankingPlatformUploadConnectionError):
            settlement._continue_or_fail(ex)

    def test_timeout_raises_upload_timeout_error(self):
        ex = requests.Timeout("timed out")
        with pytest.raises(exceptions.BankingPlatformUploadTimeoutError):
            settlement._continue_or_fail(ex)

    def test_http_error_auth_raises(self):
        resp = MagicMock(spec=requests.Response)
        resp.status_code = 401
        ex = requests.HTTPError(response=resp)
        with patch("banking_tools.settlement.api_v4.is_auth_error", return_value=True):
            with patch(
                "banking_tools.settlement.api_v4.extract_auth_error_message",
                return_value="bad",
            ):
                with pytest.raises(exceptions.BankingPlatformUploadUnauthorizedError):
                    settlement._continue_or_fail(ex)

    def test_http_error_non_auth_reraises(self):
        resp = MagicMock(spec=requests.Response)
        resp.status_code = 500
        ex = requests.HTTPError(response=resp)
        with patch("banking_tools.settlement.api_v4.is_auth_error", return_value=False):
            with pytest.raises(requests.HTTPError):
                settlement._continue_or_fail(ex)

    def test_generic_exception_reraises(self):
        ex = RuntimeError("unexpected")
        with pytest.raises(RuntimeError):
            settlement._continue_or_fail(ex)


class TestSetupIpcAllEvents:
    @patch("banking_tools.ipc.send")
    def test_fetch_offset_end_failed_events(self, mock_send):
        emitter = processor.EventEmitter()
        settlement._setup_ipc(emitter)

        emitter.emit("upload_fetch_offset", {"offset": 0})
        emitter.emit("upload_end", {"sequence_idx": 0})
        emitter.emit("upload_failed", {"sequence_idx": 0})
        called_events = [c.args[0] for c in mock_send.call_args_list]
        assert "upload_fetch_offset" in called_events
        assert "upload_end" in called_events
        assert "upload_failed" in called_events


class TestApiLoggingErrors:
    @patch.object(settlement.http, "readable_http_error", return_value="err")
    @patch.object(settlement.api_v4, "create_client_session")
    @patch.object(settlement.api_v4, "log_event")
    def test_finished_http_error_logged(
        self, mock_log_event, mock_session, mock_readable, caplog
    ):
        resp = MagicMock(spec=requests.Response)
        mock_log_event.side_effect = requests.HTTPError(response=resp)
        mock_session.return_value.__enter__ = MagicMock()
        mock_session.return_value.__exit__ = MagicMock(return_value=False)
        with patch.object(constants, "MAPILLARY_DISABLE_API_LOGGING", False):
            settlement._api_logging_finished({"size": 1}, dry_run=False)

    @patch.object(settlement.api_v4, "create_client_session")
    @patch.object(settlement.api_v4, "log_event")
    def test_finished_generic_error_logged(self, mock_log_event, mock_session):
        mock_log_event.side_effect = RuntimeError("boom")
        mock_session.return_value.__enter__ = MagicMock()
        mock_session.return_value.__exit__ = MagicMock(return_value=False)
        with patch.object(constants, "MAPILLARY_DISABLE_API_LOGGING", False):
            settlement._api_logging_finished({"size": 1}, dry_run=False)

    @patch.object(settlement.http, "readable_http_error", return_value="err")
    @patch.object(settlement.api_v4, "create_client_session")
    @patch.object(settlement.api_v4, "log_event")
    def test_failed_http_error_logged(
        self, mock_log_event, mock_session, mock_readable
    ):
        resp = MagicMock(spec=requests.Response)
        mock_log_event.side_effect = requests.HTTPError(response=resp)
        mock_session.return_value.__enter__ = MagicMock()
        mock_session.return_value.__exit__ = MagicMock(return_value=False)
        with patch.object(constants, "MAPILLARY_DISABLE_API_LOGGING", False):
            settlement._api_logging_failed(
                {"size": 1}, RuntimeError("x"), dry_run=False
            )

    @patch.object(settlement.api_v4, "create_client_session")
    @patch.object(settlement.api_v4, "log_event")
    def test_failed_generic_error_logged(self, mock_log_event, mock_session):
        mock_log_event.side_effect = ValueError("boom")
        mock_session.return_value.__enter__ = MagicMock()
        mock_session.return_value.__exit__ = MagicMock(return_value=False)
        with patch.object(constants, "MAPILLARY_DISABLE_API_LOGGING", False):
            settlement._api_logging_failed(
                {"size": 1}, RuntimeError("x"), dry_run=False
            )


class TestFindDescPath:
    def test_single_dir_returns_joined(self, tmp_path):
        result = settlement._find_desc_path([tmp_path])
        assert result.endswith(constants.IMAGE_DESCRIPTION_FILENAME)

    def test_multiple_paths_raises(self, tmp_path):
        d2 = tmp_path / "d2"
        d2.mkdir()
        with pytest.raises(exceptions.BankingPlatformBadParameterError):
            settlement._find_desc_path([tmp_path, d2])

    def test_single_file_raises(self, tmp_path):
        f = tmp_path / "f.jpg"
        f.touch()
        with pytest.raises(exceptions.BankingPlatformBadParameterError):
            settlement._find_desc_path([f])


class TestLoadValidMetadatasFromDescPath:
    def test_file_not_found_raises(self, tmp_path):
        with pytest.raises(exceptions.BankingPlatformFileNotFoundError):
            settlement._load_valid_metadatas_from_desc_path(
                [tmp_path], str(tmp_path / "missing.json")
            )

    def test_invalid_json_raises(self, tmp_path):
        bad = tmp_path / "bad.json"
        bad.write_text("{not valid json")
        with pytest.raises(exceptions.BankingPlatformInvalidDescriptionFile):
            settlement._load_valid_metadatas_from_desc_path([tmp_path], str(bad))

    @patch.object(settlement.DescriptionJSONSerializer, "deserialize_stream")
    def test_valid_file_returns_metadatas(self, mock_deser, tmp_path):
        desc = tmp_path / "desc.json"
        desc.write_text("[]")
        mock_deser.return_value = []
        result = settlement._load_valid_metadatas_from_desc_path([tmp_path], str(desc))
        assert result == []


class TestGenUploadEverything:
    @patch.object(settlement.processor, "ZipUploader")
    @patch.object(settlement.processor, "VideoUploader")
    @patch.object(settlement.processor, "ImageSequenceUploader")
    @patch.object(settlement.utils, "find_zipfiles", return_value=[])
    @patch.object(settlement.utils, "find_videos", return_value=[])
    @patch.object(settlement.utils, "find_images", return_value=[])
    def test_yields_from_all_uploaders(
        self,
        mock_find_images,
        mock_find_videos,
        mock_find_zips,
        mock_image_up,
        mock_video_up,
        mock_zip_up,
    ):
        mock_image_up.return_value.upload_images.return_value = iter([("a", "r1")])
        mock_video_up.upload_videos.return_value = iter([("b", "r2")])
        mock_zip_up.upload_zipfiles.return_value = iter([("c", "r3")])

        mly_processor = MagicMock()
        results = list(
            settlement._gen_upload_everything(mly_processor, [], [Path(".")], False)
        )
        assert len(results) == 3


class TestUploadOrchestration:
    def _patches(self):
        return {
            "_normalize_import_paths": patch.object(
                settlement, "_normalize_import_paths", return_value=[Path(".")]
            ),
            "_load_descs": patch.object(settlement, "_load_descs", return_value=[]),
            "validate": patch.object(
                settlement.config.UserItemSchemaValidator, "validate"
            ),
            "_setup_tdqm": patch.object(settlement, "_setup_tdqm"),
            "_setup_ipc": patch.object(settlement, "_setup_ipc"),
            "_setup_history": patch.object(settlement, "_setup_history"),
            "UploadOptions": patch.object(settlement.processor, "UploadOptions"),
            "Uploader": patch.object(settlement.processor, "Uploader"),
            "_api_finished": patch.object(settlement, "_api_logging_finished"),
            "_api_failed": patch.object(settlement, "_api_logging_failed"),
            "_show": patch.object(settlement, "_show_upload_summary"),
        }

    def test_successful_upload(self):
        ps = self._patches()
        with (
            ps["_normalize_import_paths"],
            ps["_load_descs"],
            ps["validate"],
            ps["_setup_tdqm"],
            ps["_setup_ipc"],
            ps["_setup_history"],
            ps["UploadOptions"],
            ps["Uploader"],
            ps["_api_finished"] as mock_finished,
            ps["_api_failed"],
            ps["_show"],
            patch.object(settlement, "_is_history_disabled", return_value=True),
            patch.object(settlement, "_summarize", return_value={}),
            patch.object(settlement, "_setup_api_stats", return_value=[{"x": 1}]),
            patch.object(settlement, "_gen_upload_everything") as mock_gen,
        ):
            result = MagicMock()
            result.error = None
            mock_gen.return_value = iter([(0, result)])

            settlement.upload(
                import_path=Path("."),
                user_items={"MAPOrganizationKey": "k", "MAPSettingsUserKey": "u"},
                num_upload_workers=1,
                dry_run=True,
            )
            mock_finished.assert_called_once()

    def test_upload_with_error_result(self):
        ps = self._patches()
        with (
            ps["_normalize_import_paths"],
            ps["_load_descs"],
            ps["validate"],
            ps["_setup_tdqm"],
            ps["_setup_ipc"],
            ps["_setup_history"],
            ps["UploadOptions"],
            ps["Uploader"],
            ps["_api_finished"],
            ps["_api_failed"],
            ps["_show"],
            patch.object(settlement, "_is_history_disabled", return_value=True),
            patch.object(settlement, "_setup_api_stats", return_value=[]),
            patch.object(settlement, "_continue_or_fail", side_effect=lambda e: e),
            patch.object(settlement, "log_exception"),
            patch.object(settlement, "_gen_upload_everything") as mock_gen,
        ):
            result = MagicMock()
            result.error = processor.SequenceError("oops")
            mock_gen.return_value = iter([(0, result)])

            # No successes, stats empty -> assertion 0 == 0 holds
            settlement.upload(
                import_path=Path("."),
                user_items={},
                num_upload_workers=1,
                dry_run=True,
            )

    def test_upload_bad_options_raises(self):
        ps = self._patches()
        with (
            ps["_normalize_import_paths"],
            ps["_load_descs"],
            ps["validate"],
            ps["_setup_tdqm"],
            ps["_setup_ipc"],
            ps["_setup_history"],
            patch.object(settlement, "_is_history_disabled", return_value=True),
            patch.object(settlement, "_setup_api_stats", return_value=[]),
            patch.object(
                settlement.processor, "UploadOptions", side_effect=ValueError("bad")
            ),
        ):
            with pytest.raises(exceptions.BankingPlatformBadParameterError):
                settlement.upload(
                    import_path=Path("."),
                    user_items={},
                    num_upload_workers=1,
                    dry_run=True,
                )
