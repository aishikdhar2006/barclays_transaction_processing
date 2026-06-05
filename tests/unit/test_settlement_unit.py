# Copyright (c) Meta Platforms, Inc. and affiliates.
#
# This source code is licensed under the BSD license found in the
# LICENSE file in the root directory of this source tree.

import json
import logging
import typing as T
from pathlib import Path
from unittest.mock import MagicMock, patch

import py.path
import pytest
import requests

from banking_tools import constants, exceptions, processor, types
from banking_tools.currency import Point
from banking_tools.settlement import (
    UploadedAlready,
    _api_logging_failed,
    _api_logging_finished,
    _continue_or_fail,
    _find_desc_path,
    _find_metadata_with_filename_existed_in,
    _is_history_disabled,
    _load_descs,
    _load_valid_metadatas_from_desc_path,
    _normalize_import_paths,
    _setup_api_stats,
    _setup_ipc,
    _setup_tdqm,
    _show_upload_summary,
    _summarize,
    log_exception,
    upload,
    zip_images,
)
from banking_tools.serializer.description import DescriptionJSONSerializer


def _make_response(status_code: int = 200, json_data: dict | None = None) -> MagicMock:
    resp = MagicMock(spec=requests.Response)
    resp.status_code = status_code
    resp.reason = "Reason"
    resp.url = "http://test.com/api"
    resp.text = "response text"
    resp.headers = {}
    resp.request = MagicMock()
    resp.request.method = "GET"
    resp.json.return_value = json_data if json_data is not None else {}
    return resp


def _make_image_metadata(
    filename: Path, seq_uuid: str | None = None
) -> types.ImageMetadata:
    return types.ImageMetadata(
        time=1.0,
        lat=58.0,
        lon=16.0,
        alt=None,
        angle=None,
        filename=filename,
        md5sum="abc123",
        MAPSequenceUUID=seq_uuid,
    )


class TestIsHistoryDisabled:
    def test_empty_history_path(self):
        with patch.object(constants, "MAPILLARY_UPLOAD_HISTORY_PATH", ""):
            assert _is_history_disabled(dry_run=False) is True

    def test_dry_run_disabled_by_default(self):
        with patch.object(constants, "MAPILLARY_UPLOAD_HISTORY_PATH", "/tmp/hist"):
            assert _is_history_disabled(dry_run=True) is True

    def test_dry_run_enabled_with_override(self):
        with (
            patch.object(constants, "MAPILLARY_UPLOAD_HISTORY_PATH", "/tmp/hist"),
            patch.object(
                constants, "MAPILLARY__ENABLE_UPLOAD_HISTORY_FOR_DRY_RUN", True
            ),
        ):
            assert _is_history_disabled(dry_run=True) is False

    def test_not_dry_run_with_path(self):
        with patch.object(constants, "MAPILLARY_UPLOAD_HISTORY_PATH", "/tmp/hist"):
            assert _is_history_disabled(dry_run=False) is False


class TestNormalizeImportPaths:
    def test_single_path(self, tmpdir: py.path.local):
        d = tmpdir.mkdir("data")
        result = _normalize_import_paths(Path(str(d)))
        assert len(result) == 1
        assert result[0] == Path(str(d))

    def test_list_of_paths(self, tmpdir: py.path.local):
        d1 = tmpdir.mkdir("d1")
        d2 = tmpdir.mkdir("d2")
        result = _normalize_import_paths([Path(str(d1)), Path(str(d2))])
        assert len(result) == 2

    def test_nonexistent_path_raises(self, tmpdir: py.path.local):
        with pytest.raises(exceptions.BankingPlatformFileNotFoundError):
            _normalize_import_paths(Path(str(tmpdir.join("nonexistent"))))


class TestFindDescPath:
    def test_single_dir(self, tmpdir: py.path.local):
        d = tmpdir.mkdir("data")
        result = _find_desc_path([Path(str(d))])
        assert constants.IMAGE_DESCRIPTION_FILENAME in result

    def test_multiple_paths_raises(self, tmpdir: py.path.local):
        d1 = tmpdir.mkdir("d1")
        d2 = tmpdir.mkdir("d2")
        with pytest.raises(
            exceptions.BankingPlatformBadParameterError, match="multiple paths"
        ):
            _find_desc_path([Path(str(d1)), Path(str(d2))])

    def test_single_file_raises(self, tmpdir: py.path.local):
        f = tmpdir.join("file.jpg")
        f.write("x")
        with pytest.raises(
            exceptions.BankingPlatformBadParameterError, match="single file"
        ):
            _find_desc_path([Path(str(f))])


class TestContinueOrFail:
    def test_sequence_error_returns(self):
        ex = UploadedAlready("already")
        assert _continue_or_fail(ex) is ex

    def test_file_not_found_returns(self):
        ex = FileNotFoundError("missing")
        assert _continue_or_fail(ex) is ex

    def test_permission_error_returns(self):
        ex = PermissionError("no perms")
        assert _continue_or_fail(ex) is ex

    def test_metadata_validation_error_returns(self):
        ex = exceptions.BankingPlatformMetadataValidationError("bad meta")
        assert _continue_or_fail(ex) is ex

    def test_connection_error_raises_upload_connection(self):
        ex = requests.ConnectionError("timeout")
        with pytest.raises(exceptions.BankingPlatformUploadConnectionError):
            _continue_or_fail(ex)

    def test_timeout_raises_upload_timeout(self):
        ex = requests.Timeout("timeout")
        with pytest.raises(exceptions.BankingPlatformUploadTimeoutError):
            _continue_or_fail(ex)

    def test_http_error_auth_raises_unauthorized(self):
        resp = MagicMock(spec=requests.Response)
        resp.status_code = 401
        resp.json.return_value = {}
        resp.text = "Unauthorized"
        ex = requests.HTTPError(response=resp)
        with pytest.raises(exceptions.BankingPlatformUploadUnauthorizedError):
            _continue_or_fail(ex)

    def test_http_error_non_auth_reraises(self):
        resp = MagicMock(spec=requests.Response)
        resp.status_code = 500
        resp.json.return_value = {}
        ex = requests.HTTPError(response=resp)
        with pytest.raises(requests.HTTPError):
            _continue_or_fail(ex)

    def test_generic_exception_reraises(self):
        ex = RuntimeError("boom")
        with pytest.raises(RuntimeError):
            _continue_or_fail(ex)


class TestSummarize:
    def test_empty_stats(self):
        result = _summarize([])
        assert result["images"] == 0
        assert result["sequences"] == 0
        assert result["speed"] == 0

    def test_with_stats(self):
        stat = {
            "sequence_image_count": 5,
            "entity_size": 1024 * 1024,
            "upload_first_offset": 0,
            "upload_total_time": 2.0,
        }
        result = _summarize([stat])
        assert result["images"] == 5
        assert result["sequences"] == 1
        assert result["size"] > 0
        assert result["speed"] > 0


class TestShowUploadSummary:
    def test_empty_stats_and_errors(self, caplog):
        with caplog.at_level(logging.INFO):
            _show_upload_summary([], [])
        assert "Nothing uploaded" in caplog.text

    def test_with_uploaded_already_errors(self, caplog):
        errors = [UploadedAlready("skip1"), UploadedAlready("skip2")]
        with caplog.at_level(logging.INFO):
            _show_upload_summary([], errors)
        assert "Skipped 2 already uploaded" in caplog.text

    def test_with_stats(self, caplog):
        stat = {
            "sequence_image_count": 3,
            "entity_size": 1024 * 1024,
            "upload_first_offset": 0,
            "upload_total_time": 1.0,
            "file_type": "image",
        }
        with caplog.at_level(logging.INFO):
            _show_upload_summary([stat], [])
        assert "1 sequences uploaded" in caplog.text


class TestLogException:
    def test_uploaded_already(self, caplog):
        with caplog.at_level(logging.INFO):
            log_exception(UploadedAlready("done"))
        assert "UploadedAlready" in caplog.text

    def test_http_error(self, caplog):
        resp = _make_response(500)
        ex = requests.HTTPError(response=resp)
        with caplog.at_level(logging.ERROR):
            log_exception(ex)
        assert "HTTPError" in caplog.text

    def test_generic_error(self, caplog):
        with caplog.at_level(logging.ERROR):
            log_exception(RuntimeError("boom"))
        assert "RuntimeError" in caplog.text


class TestApiLogging:
    def test_finished_dry_run_noop(self):
        _api_logging_finished({}, dry_run=True)

    def test_finished_disabled_noop(self):
        with patch.object(constants, "MAPILLARY_DISABLE_API_LOGGING", True):
            _api_logging_finished({}, dry_run=False)

    @patch("banking_tools.settlement.api_v4.create_client_session")
    @patch("banking_tools.settlement.api_v4.log_event")
    def test_finished_success(self, mock_log, mock_session):
        mock_session.return_value.__enter__ = MagicMock()
        mock_session.return_value.__exit__ = MagicMock(return_value=False)
        with patch.object(constants, "MAPILLARY_DISABLE_API_LOGGING", False):
            _api_logging_finished({"key": "val"}, dry_run=False)
        mock_log.assert_called_once()

    @patch("banking_tools.settlement.api_v4.create_client_session")
    @patch("banking_tools.settlement.api_v4.log_event")
    def test_finished_http_error_logged(self, mock_log, mock_session, caplog):
        mock_log.side_effect = requests.HTTPError(response=_make_response(500))
        mock_session.return_value.__enter__ = MagicMock()
        mock_session.return_value.__exit__ = MagicMock(return_value=False)
        with (
            patch.object(constants, "MAPILLARY_DISABLE_API_LOGGING", False),
            caplog.at_level(logging.WARNING),
        ):
            _api_logging_finished({}, dry_run=False)
        assert "HTTPError" in caplog.text

    def test_failed_dry_run_noop(self):
        _api_logging_failed({}, RuntimeError("x"), dry_run=True)

    def test_failed_disabled_noop(self):
        with patch.object(constants, "MAPILLARY_DISABLE_API_LOGGING", True):
            _api_logging_failed({}, RuntimeError("x"), dry_run=False)

    @patch("banking_tools.settlement.api_v4.create_client_session")
    @patch("banking_tools.settlement.api_v4.log_event")
    def test_failed_success(self, mock_log, mock_session):
        mock_session.return_value.__enter__ = MagicMock()
        mock_session.return_value.__exit__ = MagicMock(return_value=False)
        with patch.object(constants, "MAPILLARY_DISABLE_API_LOGGING", False):
            _api_logging_failed({"key": "val"}, RuntimeError("x"), dry_run=False)
        mock_log.assert_called_once()

    @patch("banking_tools.settlement.api_v4.create_client_session")
    @patch("banking_tools.settlement.api_v4.log_event", side_effect=Exception("oops"))
    def test_failed_generic_error_logged(self, mock_log, mock_session, caplog):
        mock_session.return_value.__enter__ = MagicMock()
        mock_session.return_value.__exit__ = MagicMock(return_value=False)
        with (
            patch.object(constants, "MAPILLARY_DISABLE_API_LOGGING", False),
            caplog.at_level(logging.WARNING),
        ):
            _api_logging_failed({}, RuntimeError("x"), dry_run=False)
        assert "Error from logging" in caplog.text


class TestFindMetadataWithFilenameExistedIn:
    def test_filters_existing(self, tmpdir: py.path.local):
        f1 = tmpdir.join("a.jpg")
        f1.write("x")
        f2 = tmpdir.join("b.jpg")
        f2.write("x")
        m1 = _make_image_metadata(Path(str(f1)))
        m2 = _make_image_metadata(Path(str(f2)))
        result = _find_metadata_with_filename_existed_in([m1, m2], [Path(str(f1))])
        assert len(result) == 1
        assert result[0].filename == Path(str(f1))


class TestLoadDescs:
    def test_from_process_metadatas(self, tmpdir: py.path.local):
        f = tmpdir.join("a.jpg")
        f.write("x")
        m = _make_image_metadata(Path(str(f)), seq_uuid=None)
        result = _load_descs([m], [Path(str(tmpdir))], None)
        assert len(result) == 1
        assert result[0].MAPSequenceUUID is not None

    def test_from_process_with_existing_uuid(self, tmpdir: py.path.local):
        f = tmpdir.join("a.jpg")
        f.write("x")
        m = _make_image_metadata(Path(str(f)), seq_uuid="existing-uuid")
        result = _load_descs([m], [Path(str(tmpdir))], None)
        assert result[0].MAPSequenceUUID == "existing-uuid"


class TestLoadValidMetadatasFromDescPath:
    def test_file_not_found_raises(self):
        with pytest.raises(exceptions.BankingPlatformFileNotFoundError):
            _load_valid_metadatas_from_desc_path(
                [Path("/tmp")], "/nonexistent/desc.json"
            )

    def test_valid_desc_file(self, tmpdir: py.path.local):
        f = tmpdir.join("a.jpg")
        f.write("x")
        m = _make_image_metadata(Path(str(f)), seq_uuid="uuid1")
        data = DescriptionJSONSerializer.serialize([m])
        desc = tmpdir.join("desc.json")
        desc.write_binary(data)
        result = _load_valid_metadatas_from_desc_path([Path(str(tmpdir))], str(desc))
        assert len(result) == 1

    def test_invalid_json_raises(self, tmpdir: py.path.local):
        desc = tmpdir.join("bad.json")
        desc.write("not json at all{{{")
        with pytest.raises(exceptions.BankingPlatformInvalidDescriptionFile):
            _load_valid_metadatas_from_desc_path([Path(str(tmpdir))], str(desc))


class TestSetupApiStats:
    def test_emitter_collects_stats(self):
        emitter = processor.EventEmitter()
        stats = _setup_api_stats(emitter)

        payload: T.Dict[str, T.Any] = {
            "sequence_md5sum": "md5",
            "file_type": "image",
            "total_sequence_count": 1,
            "sequence_idx": 0,
            "entity_size": 1024,
            "offset": 0,
            "chunk_size": 0,
            "begin_offset": None,
            "retries": 0,
            "cluster_id": "c1",
        }

        emitter.emit("upload_start", payload)
        assert "upload_start_time" in payload
        assert "upload_total_time" in payload

        emitter.emit("upload_fetch_offset", payload)
        assert "upload_last_restart_time" in payload

        payload["offset"] = 1024
        emitter.emit("upload_end", payload)
        assert "upload_end_time" in payload

        emitter.emit("upload_finished", payload)
        assert len(stats) == 1


class TestSetupTdqm:
    def test_tqdm_lifecycle(self):
        emitter = processor.EventEmitter()
        _setup_tdqm(emitter)

        payload: T.Dict[str, T.Any] = {
            "sequence_md5sum": "md5",
            "file_type": "image",
            "total_sequence_count": 1,
            "sequence_idx": 0,
            "entity_size": 1024,
            "offset": 0,
            "chunk_size": 256,
            "begin_offset": None,
            "retries": 0,
            "cluster_id": "c1",
            "import_path": "/tmp/test.jpg",
        }

        emitter.emit("upload_start", payload)
        emitter.emit("upload_progress", payload)
        emitter.emit("upload_end", payload)


class TestSetupIpc:
    @patch("banking_tools.settlement.ipc.send")
    def test_ipc_events(self, mock_send):
        emitter = processor.EventEmitter()
        _setup_ipc(emitter)

        payload: T.Dict[str, T.Any] = {
            "sequence_md5sum": "md5",
            "entity_size": 1024,
            "offset": 0,
            "chunk_size": 0,
            "total_sequence_count": 1,
            "sequence_idx": 0,
        }

        emitter.emit("upload_start", payload)
        emitter.emit("upload_fetch_offset", payload)
        emitter.emit("upload_progress", payload)
        emitter.emit("upload_end", payload)
        emitter.emit("upload_failed", payload)
        assert mock_send.call_count == 5


class TestZipImages:
    def test_nonexistent_import_raises(self, tmpdir: py.path.local):
        with pytest.raises(exceptions.BankingPlatformFileNotFoundError):
            zip_images(Path("/nonexistent"), Path(str(tmpdir)))


class TestUploadDryRun:
    def test_upload_empty_dry_run(self, tmpdir: py.path.local):
        d = tmpdir.mkdir("data")
        user_items = {"user_upload_token": "test_token"}
        upload(
            import_path=Path(str(d)),
            user_items=user_items,
            num_upload_workers=1,
            _metadatas_from_process=[],
            dry_run=True,
        )

    def test_upload_bad_workers_raises(self, tmpdir: py.path.local):
        d = tmpdir.mkdir("data")
        user_items = {"user_upload_token": "test_token"}
        with pytest.raises(exceptions.BankingPlatformBadParameterError):
            upload(
                import_path=Path(str(d)),
                user_items=user_items,
                num_upload_workers=0,
                _metadatas_from_process=[],
                dry_run=True,
            )
