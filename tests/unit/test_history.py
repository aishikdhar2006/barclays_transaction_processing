# Copyright (c) Meta Platforms, Inc. and affiliates.
#
# This source code is licensed under the BSD license found in the
# LICENSE file in the root directory of this source tree.

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from banking_tools import constants, history


class TestValidateHexdigits:
    def test_valid_md5sum(self):
        history._validate_hexdigits("abcdef1234567890")

    def test_too_short(self):
        with pytest.raises(ValueError, match="Invalid md5sum"):
            history._validate_hexdigits("ab")

    def test_non_hex(self):
        with pytest.raises(ValueError, match="Invalid md5sum"):
            history._validate_hexdigits("ghijklmn")


class TestHistoryDescPath:
    @patch.object(constants, "MAPILLARY_UPLOAD_HISTORY_PATH", "/tmp/hist")
    def test_path_structure(self):
        path = history.history_desc_path("abcdef1234")
        assert path == Path("/tmp/hist/ab/cdef1234.json")


class TestReadHistoryRecord:
    @patch.object(constants, "MAPILLARY_UPLOAD_HISTORY_PATH", "")
    def test_empty_path_returns_none(self):
        result = history.read_history_record("abcdef1234")
        assert result is None

    @patch.object(constants, "MAPILLARY_UPLOAD_HISTORY_PATH", "/tmp/hist_test_read")
    def test_file_not_found(self, tmp_path):
        result = history.read_history_record("abcdef1234")
        assert result is None

    def test_valid_record(self, tmp_path):
        hist_dir = tmp_path / "ab"
        hist_dir.mkdir()
        hist_file = hist_dir / "cdef1234.json"
        hist_file.write_text(
            json.dumps({"params": {}, "summary": {"upload_end_time": 100}})
        )

        with patch.object(constants, "MAPILLARY_UPLOAD_HISTORY_PATH", str(tmp_path)):
            result = history.read_history_record("abcdef1234")
        assert result is not None
        assert result["summary"]["upload_end_time"] == 100

    def test_corrupted_json(self, tmp_path):
        hist_dir = tmp_path / "ab"
        hist_dir.mkdir()
        hist_file = hist_dir / "cdef1234.json"
        hist_file.write_text("not json{{{")

        with patch.object(constants, "MAPILLARY_UPLOAD_HISTORY_PATH", str(tmp_path)):
            result = history.read_history_record("abcdef1234")
        assert result is None


class TestWriteHistory:
    @patch.object(constants, "MAPILLARY_UPLOAD_HISTORY_PATH", "")
    def test_empty_path_does_nothing(self):
        history.write_history("abcdef1234", {}, {})

    def test_writes_to_file(self, tmp_path):
        with patch.object(constants, "MAPILLARY_UPLOAD_HISTORY_PATH", str(tmp_path)):
            history.write_history("abcdef1234", {"key": "val"}, {"result": "ok"})
        path = tmp_path / "ab" / "cdef1234.json"
        assert path.is_file()
        data = json.loads(path.read_text())
        assert data["params"]["key"] == "val"
        assert data["summary"]["result"] == "ok"
