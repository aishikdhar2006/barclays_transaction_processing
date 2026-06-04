# Copyright (c) Meta Platforms, Inc. and affiliates.
#
# This source code is licensed under the BSD license found in the
# LICENSE file in the root directory of this source tree.

from pathlib import Path
from unittest.mock import MagicMock, patch

import requests

from banking_tools import api_v4, constants, processor


class TestParseRetryAfterFromHeader:
    def test_integer_value(self):
        resp = MagicMock(spec=requests.Response)
        resp.headers = {"Retry-After": "5"}
        result = processor._parse_retry_after_from_header(resp)
        assert result == 5

    def test_negative_value_clamped_to_zero(self):
        resp = MagicMock(spec=requests.Response)
        resp.headers = {"Retry-After": "-1"}
        result = processor._parse_retry_after_from_header(resp)
        assert result == 0

    def test_missing_header(self):
        resp = MagicMock(spec=requests.Response)
        resp.headers = {}
        result = processor._parse_retry_after_from_header(resp)
        assert result is None

    def test_date_in_past(self):
        resp = MagicMock(spec=requests.Response)
        resp.headers = {"Retry-After": "Wed, 21 Oct 2015 07:28:00 GMT"}
        result = processor._parse_retry_after_from_header(resp)
        assert result == 0

    def test_invalid_date_string(self):
        resp = MagicMock(spec=requests.Response)
        resp.headers = {"Retry-After": "not-a-date-or-number"}
        result = processor._parse_retry_after_from_header(resp)
        assert result is None


class TestParseBackoff:
    def test_valid_integer(self):
        assert processor._parse_backoff(10000) == 10000

    def test_string_integer(self):
        assert processor._parse_backoff("5000") == 5000

    def test_none(self):
        assert processor._parse_backoff(None) is None

    def test_invalid_string(self):
        assert processor._parse_backoff("not_a_number") is None


class TestIsRetriableException:
    def test_connection_error(self):
        ex = requests.ConnectionError("connection refused")
        retriable, delay = processor._is_retriable_exception(ex)
        assert retriable is True
        assert delay == 0

    def test_timeout(self):
        ex = requests.Timeout("timed out")
        retriable, delay = processor._is_retriable_exception(ex)
        assert retriable is True
        assert delay == 0

    def test_429_with_retry_after(self):
        resp = MagicMock(spec=requests.Response)
        resp.status_code = 429
        resp.headers = {"Retry-After": "3"}
        resp.json.side_effect = requests.JSONDecodeError("", "", 0)
        ex = requests.HTTPError(response=resp)
        retriable, delay = processor._is_retriable_exception(ex)
        assert retriable is True
        assert delay == 3

    def test_429_with_backoff(self):
        resp = MagicMock(spec=requests.Response)
        resp.status_code = 429
        resp.headers = {}
        resp.json.return_value = {"backoff": 20000}
        ex = requests.HTTPError(response=resp)
        retriable, delay = processor._is_retriable_exception(ex)
        assert retriable is True
        assert delay == 20

    def test_400_retriable_type(self):
        resp = MagicMock(spec=requests.Response)
        resp.status_code = 400
        resp.headers = {}
        resp.json.return_value = {
            "debug_info": {"retriable": True, "type": "SomeError"}
        }
        ex = requests.HTTPError(response=resp)
        retriable, delay = processor._is_retriable_exception(ex)
        assert retriable is True

    def test_400_non_retriable(self):
        resp = MagicMock(spec=requests.Response)
        resp.status_code = 400
        resp.headers = {}
        resp.json.return_value = {
            "debug_info": {"retriable": False, "type": "BadRequest"}
        }
        ex = requests.HTTPError(response=resp)
        retriable, delay = processor._is_retriable_exception(ex)
        assert retriable is False

    def test_400_rate_limit_error(self):
        resp = MagicMock(spec=requests.Response)
        resp.status_code = 400
        resp.headers = {}
        resp.json.return_value = {
            "debug_info": {"retriable": False, "type": "RequestRateLimitedError"},
            "backoff": 5000,
        }
        ex = requests.HTTPError(response=resp)
        retriable, delay = processor._is_retriable_exception(ex)
        assert retriable is True
        assert delay == 5

    def test_500_error(self):
        resp = MagicMock(spec=requests.Response)
        resp.status_code = 500
        resp.headers = {}
        ex = requests.HTTPError(response=resp)
        retriable, delay = processor._is_retriable_exception(ex)
        assert retriable is True

    def test_non_retriable_exception(self):
        ex = ValueError("some error")
        retriable, delay = processor._is_retriable_exception(ex)
        assert retriable is False


class TestSuffixSessionKey:
    def test_zip_suffix(self):
        result = processor._suffix_session_key("abc123", api_v4.ClusterFileType.ZIP)
        assert result == "mly_tools_abc123.zip"

    def test_camm_suffix(self):
        result = processor._suffix_session_key("abc123", api_v4.ClusterFileType.CAMM)
        assert result == "mly_tools_abc123.mp4"

    def test_uuid_key(self):
        result = processor._suffix_session_key(
            "uuid_abc123", api_v4.ClusterFileType.ZIP
        )
        assert result == "mly_tools_uuid_abc123.zip"
        assert processor._is_uuid(result)


class TestIsUuid:
    def test_uuid_prefix(self):
        assert processor._is_uuid("uuid_abc123") is True

    def test_mly_tools_uuid_prefix(self):
        assert processor._is_uuid("mly_tools_uuid_abc123") is True

    def test_not_uuid(self):
        assert processor._is_uuid("regular_key") is False


class TestPrefixedUuid4:
    def test_generates_uuid(self):
        result = processor._prefixed_uuid4()
        assert result.startswith("uuid_")
        assert processor._is_uuid(result)


class TestBuildUploadCachePath:
    def test_basic_path(self):
        user_items = {"user_upload_token": "tok", "MAPSettingsUserKey": "user123"}
        opts = processor.UploadOptions(user_items=user_items)
        with patch.object(constants, "UPLOAD_CACHE_DIR", "/tmp/test_cache"):
            path = processor._build_upload_cache_path(opts)
        assert "cached_file_handles" in str(path)
        assert str(Path("/tmp/test_cache")) in str(path)


class TestMaybeCreatePersistentCacheInstance:
    def test_dry_run_returns_none(self):
        user_items = {"user_upload_token": "tok", "MAPSettingsUserKey": "user123"}
        opts = processor.UploadOptions(user_items=user_items, dry_run=True)
        result = processor._maybe_create_persistent_cache_instance(opts)
        assert result is None

    def test_empty_cache_dir_returns_none(self):
        user_items = {"user_upload_token": "tok", "MAPSettingsUserKey": "user123"}
        opts = processor.UploadOptions(user_items=user_items)
        with patch.object(constants, "UPLOAD_CACHE_DIR", ""):
            result = processor._maybe_create_persistent_cache_instance(opts)
        assert result is None

    def test_creates_cache(self, tmp_path):
        user_items = {"user_upload_token": "tok", "MAPSettingsUserKey": "user123"}
        opts = processor.UploadOptions(user_items=user_items)
        with patch.object(constants, "UPLOAD_CACHE_DIR", str(tmp_path)):
            result = processor._maybe_create_persistent_cache_instance(opts)
        assert result is not None

    def test_custom_cache_path(self, tmp_path):
        user_items = {"user_upload_token": "tok", "MAPSettingsUserKey": "user123"}
        cache_path = tmp_path / "my_cache"
        opts = processor.UploadOptions(
            user_items=user_items, upload_cache_path=cache_path
        )
        result = processor._maybe_create_persistent_cache_instance(opts)
        assert result is not None
