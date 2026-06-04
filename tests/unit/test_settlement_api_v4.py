# Copyright (c) Meta Platforms, Inc. and affiliates.
#
# This source code is licensed under the BSD license found in the
# LICENSE file in the root directory of this source tree.

import io
from unittest.mock import MagicMock

import pytest
import requests

from banking_tools import settlement_api_v4


class TestChunkizeByteStream:
    def test_basic_chunking(self):
        stream = io.BytesIO(b"foobar")
        chunks = list(settlement_api_v4.UploadService.chunkize_byte_stream(stream, 3))
        assert chunks == [b"foo", b"bar"]

    def test_chunk_larger_than_stream(self):
        stream = io.BytesIO(b"foo")
        chunks = list(settlement_api_v4.UploadService.chunkize_byte_stream(stream, 10))
        assert chunks == [b"foo"]

    def test_single_byte_chunks(self):
        stream = io.BytesIO(b"abc")
        chunks = list(settlement_api_v4.UploadService.chunkize_byte_stream(stream, 1))
        assert chunks == [b"a", b"b", b"c"]

    def test_empty_stream(self):
        stream = io.BytesIO(b"")
        chunks = list(settlement_api_v4.UploadService.chunkize_byte_stream(stream, 10))
        assert chunks == []

    def test_zero_chunk_size_raises(self):
        stream = io.BytesIO(b"foo")
        with pytest.raises(ValueError, match="positive"):
            list(settlement_api_v4.UploadService.chunkize_byte_stream(stream, 0))


class TestShiftChunks:
    def test_zero_offset(self):
        chunks = [b"foo", b"bar"]
        result = list(settlement_api_v4.UploadService.shift_chunks(chunks, 0))
        assert result == [b"foo", b"bar"]

    def test_partial_first_chunk(self):
        chunks = [b"foo", b"bar"]
        result = list(settlement_api_v4.UploadService.shift_chunks(chunks, 1))
        assert result == [b"oo", b"bar"]

    def test_exact_first_chunk(self):
        chunks = [b"foo", b"bar"]
        result = list(settlement_api_v4.UploadService.shift_chunks(chunks, 3))
        assert result == [b"bar"]

    def test_beyond_all_chunks(self):
        chunks = [b"foo", b"bar"]
        result = list(settlement_api_v4.UploadService.shift_chunks(chunks, 7))
        assert result == []

    def test_empty_chunks(self):
        result = list(settlement_api_v4.UploadService.shift_chunks([], 0))
        assert result == []

    def test_negative_offset_raises(self):
        with pytest.raises(ValueError, match="non-negative"):
            list(settlement_api_v4.UploadService.shift_chunks([b"foo"], -1))


class TestFakeUploadService:
    def test_upload_and_fetch_offset(self, tmp_path):
        session = MagicMock(spec=requests.Session)
        svc = settlement_api_v4.FakeUploadService(
            session, "test_session", upload_path=tmp_path
        )
        assert svc.fetch_offset() == 0

        handle = svc.upload_shifted_chunks([b"hello", b"world"], 0)
        assert handle is not None
        assert len(handle) == 32  # uuid4 hex
        assert svc.fetch_offset() == 10

    def test_upload_path_property(self, tmp_path):
        session = MagicMock(spec=requests.Session)
        svc = settlement_api_v4.FakeUploadService(
            session, "test_session", upload_path=tmp_path
        )
        assert svc.upload_path == tmp_path

    def test_wrong_offset_raises(self, tmp_path):
        session = MagicMock(spec=requests.Session)
        svc = settlement_api_v4.FakeUploadService(
            session, "test_session", upload_path=tmp_path
        )
        with pytest.raises(ValueError, match="Expect offset"):
            svc.upload_shifted_chunks([b"hello"], 5)

    def test_default_upload_path(self):
        session = MagicMock(spec=requests.Session)
        svc = settlement_api_v4.FakeUploadService(session, "test_session")
        assert "banking_public_uploads" in str(svc.upload_path)

    def test_transient_error_ratio(self, tmp_path):
        session = MagicMock(spec=requests.Session)
        svc = settlement_api_v4.FakeUploadService(
            session, "test_err", upload_path=tmp_path, transient_error_ratio=1.0
        )
        with pytest.raises(requests.ConnectionError, match="Transient"):
            svc.fetch_offset()
