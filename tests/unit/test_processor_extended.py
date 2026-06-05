# Copyright (c) Meta Platforms, Inc. and affiliates.
#
# This source code is licensed under the BSD license found in the
# LICENSE file in the root directory of this source tree.

import dataclasses
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests

from banking_tools import config, processor


class TestEventEmitter:
    def test_on_and_emit(self):
        emitter = processor.EventEmitter()
        calls = []

        @emitter.on("upload_start")
        def handler(payload):
            calls.append(payload)

        emitter.emit("upload_start", {"data": "test"})
        assert len(calls) == 1
        assert calls[0]["data"] == "test"

    def test_multiple_handlers(self):
        emitter = processor.EventEmitter()
        calls = []

        @emitter.on("upload_end")
        def handler1(payload):
            calls.append("h1")

        @emitter.on("upload_end")
        def handler2(payload):
            calls.append("h2")

        emitter.emit("upload_end", {})
        assert calls == ["h1", "h2"]

    def test_emit_no_handlers(self):
        emitter = processor.EventEmitter()
        emitter.emit("upload_start", {})

    def test_emit_unknown_event(self):
        emitter = processor.EventEmitter()
        emitter.emit("upload_progress", {"chunk_size": 100})


class TestUploadOptions:
    def test_valid_options(self):
        opts = processor.UploadOptions(
            {"user_upload_token": "tok"},
            num_upload_workers=2,
            dry_run=True,
        )
        assert opts.num_upload_workers == 2
        assert opts.dry_run is True

    def test_zero_workers_raises(self):
        with pytest.raises(ValueError, match="positive num_upload_workers"):
            processor.UploadOptions(
                {"user_upload_token": "tok"},
                num_upload_workers=0,
            )

    def test_negative_workers_raises(self):
        with pytest.raises(ValueError, match="positive num_upload_workers"):
            processor.UploadOptions(
                {"user_upload_token": "tok"},
                num_upload_workers=-1,
            )

    def test_zero_chunk_size_raises(self):
        with pytest.raises(ValueError, match="positive chunk_size"):
            processor.UploadOptions(
                {"user_upload_token": "tok"},
                chunk_size=0,
            )


class TestUploadResult:
    def test_success(self):
        r = processor.UploadResult(result="cluster_123")
        assert r.result == "cluster_123"
        assert r.error is None

    def test_error(self):
        ex = RuntimeError("boom")
        r = processor.UploadResult(error=ex)
        assert r.result is None
        assert r.error is ex

    def test_defaults(self):
        r = processor.UploadResult()
        assert r.result is None
        assert r.error is None


class TestSequenceError:
    def test_create(self):
        err = processor.SequenceError("test error")
        assert str(err) == "test error"


class TestUploader:
    def test_create(self):
        opts = processor.UploadOptions(
            {"user_upload_token": "tok"},
            dry_run=True,
        )
        uploader = processor.Uploader(opts)
        assert uploader.upload_options is opts
        assert uploader.emitter is not None

    def test_create_with_emitter(self):
        emitter = processor.EventEmitter()
        opts = processor.UploadOptions(
            {"user_upload_token": "tok"},
            dry_run=True,
        )
        uploader = processor.Uploader(opts, emitter=emitter)
        assert uploader.emitter is emitter

    def test_upload_name(self):
        payload = {
            "import_path": "/tmp/test.jpg",
            "file_type": "image",
            "sequence_idx": 0,
            "total_sequence_count": 1,
        }
        name = processor.Uploader._upload_name(payload)
        assert isinstance(name, str)


def _http_error(status_code: int, content: bytes = b"", headers=None):
    resp = requests.Response()
    resp._content = content
    resp.status_code = status_code
    if headers:
        resp.headers.update(headers)
    return requests.HTTPError("error", response=resp)


class TestIsRetriableException:
    def test_connection_error(self):
        assert processor._is_retriable_exception(requests.ConnectionError()) == (
            True,
            0,
        )

    def test_timeout(self):
        assert processor._is_retriable_exception(requests.Timeout()) == (True, 0)

    def test_400_not_retriable(self):
        ex = _http_error(400, b"foo")
        assert processor._is_retriable_exception(ex) == (False, 0)

    def test_429_default(self):
        ex = _http_error(429, b"foo")
        assert processor._is_retriable_exception(ex) == (True, 10)

    def test_429_with_backoff(self):
        ex = _http_error(429, b'{"backoff": 12000}')
        assert processor._is_retriable_exception(ex) == (True, 12)

    def test_500_retriable(self):
        ex = _http_error(503, b"foo", {"Retry-After": "5"})
        assert processor._is_retriable_exception(ex) == (True, 5)

    def test_400_rate_limited_retriable(self):
        ex = _http_error(
            400,
            b'{"backoff": 13000, "debug_info": {"type": "RequestRateLimitedError"}}',
        )
        assert processor._is_retriable_exception(ex) == (True, 13)

    def test_400_debug_info_retriable(self):
        ex = _http_error(400, b'{"debug_info": {"retriable": true}}')
        assert processor._is_retriable_exception(ex) == (True, 0)

    def test_non_http_error(self):
        assert processor._is_retriable_exception(ValueError("x")) == (False, 0)


class TestIsImmediateRetriableException:
    def test_412_retriable(self):
        ex = _http_error(412, b'{"debug_info": {"retriable": true}}')
        assert processor._is_immediate_retriable_exception(ex) is True

    def test_412_not_retriable(self):
        ex = _http_error(412, b'{"debug_info": {"retriable": false}}')
        assert processor._is_immediate_retriable_exception(ex) is False

    def test_412_invalid_json(self):
        ex = _http_error(412, b"not json")
        assert processor._is_immediate_retriable_exception(ex) is False

    def test_other_status(self):
        ex = _http_error(400, b"foo")
        assert processor._is_immediate_retriable_exception(ex) is False


class TestParseBackoff:
    def test_valid_int(self):
        assert processor._parse_backoff(5000) == 5000

    def test_string_number(self):
        assert processor._parse_backoff("5000") == 5000

    def test_none(self):
        assert processor._parse_backoff(None) is None

    def test_invalid(self):
        assert processor._parse_backoff("foo") is None


class TestParseRetryAfterFromHeader:
    def test_integer_seconds(self):
        resp = requests.Response()
        resp.headers.update({"Retry-After": "5"})
        assert processor._parse_retry_after_from_header(resp) == 5

    def test_negative_clamped(self):
        resp = requests.Response()
        resp.headers.update({"Retry-After": "-1"})
        assert processor._parse_retry_after_from_header(resp) == 0

    def test_missing(self):
        resp = requests.Response()
        assert processor._parse_retry_after_from_header(resp) is None

    def test_http_date_past(self):
        resp = requests.Response()
        resp.headers.update({"Retry-After": "Wed, 21 Oct 2015 07:28:00 GMT"})
        assert processor._parse_retry_after_from_header(resp) == 0

    def test_invalid_value(self):
        resp = requests.Response()
        resp.headers.update({"Retry-After": "not-a-date"})
        assert processor._parse_retry_after_from_header(resp) is None


class TestUuidHelpers:
    def test_is_uuid_true(self):
        assert processor._is_uuid("uuid_abc123") is True
        assert processor._is_uuid("mly_tools_uuid_abc") is True

    def test_is_uuid_false(self):
        assert processor._is_uuid("abc123") is False

    def test_prefixed_uuid4(self):
        key = processor._prefixed_uuid4()
        assert key.startswith("uuid_")
        assert processor._is_uuid(key)

    def test_suffix_session_key_image(self):
        from banking_tools import types as bt_types

        result = processor._suffix_session_key("uuid_abc", bt_types.FileType.IMAGE)
        assert result == "mly_tools_uuid_abc.jpg"

    def test_suffix_session_key_video(self):
        from banking_tools import types as bt_types

        result = processor._suffix_session_key("uuid_x", bt_types.FileType.VIDEO)
        assert result.endswith(".mp4")


class TestBuildUploadCachePath:
    def test_builds_path(self):
        opts = processor.UploadOptions(
            {"user_upload_token": "tok", "MAPSettingsUserKey": "key1"},
            dry_run=True,
        )
        path = processor._build_upload_cache_path(opts)
        assert isinstance(path, Path)
        assert "cached_file_handles" in str(path)


class TestMaybeCreatePersistentCache:
    def test_dry_run_returns_none(self):
        opts = processor.UploadOptions(
            {"user_upload_token": "tok"},
            dry_run=True,
        )
        assert processor._maybe_create_persistent_cache_instance(opts) is None
