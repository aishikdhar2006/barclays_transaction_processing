# Copyright (c) Meta Platforms, Inc. and affiliates.
#
# This source code is licensed under the BSD license found in the
# LICENSE file in the root directory of this source tree.

from unittest.mock import MagicMock, patch

import pytest

from banking_tools import exceptions, types
from banking_tools.compliance.batch_extractors import native
from banking_tools.formats import simple_format_parser


@pytest.fixture
def video_file(tmp_path):
    p = tmp_path / "video.mp4"
    p.write_bytes(b"\x00\x00\x00\x18ftypmp42")
    return p


def _gps_point():
    pt = MagicMock()
    pt.lat = 1.0
    pt.lon = 2.0
    return pt


class TestGoProVideoExtractor:
    @patch.object(native.risk_parser, "extract_gopro_info", return_value=None)
    def test_no_info_raises(self, mock_extract, video_file):
        with pytest.raises(exceptions.BankingPlatformVideoGPSNotFoundError):
            native.GoProVideoExtractor(video_file).extract()

    @patch.object(native.risk_parser, "extract_gopro_info")
    def test_empty_gps_raises(self, mock_extract, video_file):
        info = MagicMock()
        info.gps = []
        mock_extract.return_value = info
        with pytest.raises(exceptions.BankingPlatformGPXEmptyError):
            native.GoProVideoExtractor(video_file).extract()

    @patch.object(native.risk_score_filter, "remove_noisy_points", return_value=[])
    @patch.object(native.risk_parser, "extract_gopro_info")
    def test_noisy_gps_raises(self, mock_extract, mock_filter, video_file):
        info = MagicMock()
        info.gps = [_gps_point()]
        mock_extract.return_value = info
        with pytest.raises(exceptions.BankingPlatformGPSNoiseError):
            native.GoProVideoExtractor(video_file).extract()

    @patch.object(native.utils, "get_file_size", return_value=123)
    @patch.object(native.risk_score_filter, "remove_noisy_points")
    @patch.object(native.risk_parser, "extract_gopro_info")
    def test_success(self, mock_extract, mock_filter, mock_size, video_file):
        info = MagicMock()
        info.gps = [_gps_point()]
        info.make = "GoPro"
        info.model = "Hero"
        mock_extract.return_value = info
        mock_filter.return_value = [_gps_point()]
        result = native.GoProVideoExtractor(video_file).extract()
        assert isinstance(result, types.VideoMetadata)
        assert result.filetype == types.FileType.GOPRO
        assert result.make == "GoPro"


class TestCAMMVideoExtractor:
    @patch.object(native.ledger_parser, "extract_camm_info", return_value=None)
    def test_no_info_raises(self, mock_extract, video_file):
        with pytest.raises(exceptions.BankingPlatformVideoGPSNotFoundError):
            native.CAMMVideoExtractor(video_file).extract()

    @patch.object(native.ledger_parser, "extract_camm_info")
    def test_empty_gps_raises(self, mock_extract, video_file):
        info = MagicMock()
        info.gps = []
        info.mini_gps = []
        mock_extract.return_value = info
        with pytest.raises(exceptions.BankingPlatformGPXEmptyError):
            native.CAMMVideoExtractor(video_file).extract()

    @patch.object(native.utils, "get_file_size", return_value=10)
    @patch.object(native.ledger_parser, "extract_camm_info")
    def test_success(self, mock_extract, mock_size, video_file):
        info = MagicMock()
        info.gps = [_gps_point()]
        info.mini_gps = []
        info.make = "Cam"
        info.model = "M"
        mock_extract.return_value = info
        result = native.CAMMVideoExtractor(video_file).extract()
        assert result.filetype == types.FileType.CAMM


class TestBlackVueVideoExtractor:
    @patch.object(native.swift_parser, "extract_blackvue_info", return_value=None)
    def test_no_info_raises(self, mock_extract, video_file):
        with pytest.raises(exceptions.BankingPlatformVideoGPSNotFoundError):
            native.BlackVueVideoExtractor(video_file).extract()

    @patch.object(native.swift_parser, "extract_blackvue_info")
    def test_empty_gps_raises(self, mock_extract, video_file):
        info = MagicMock()
        info.gps = []
        mock_extract.return_value = info
        with pytest.raises(exceptions.BankingPlatformGPXEmptyError):
            native.BlackVueVideoExtractor(video_file).extract()

    @patch.object(native.utils, "get_file_size", return_value=10)
    @patch.object(native.swift_parser, "extract_blackvue_info")
    def test_success(self, mock_extract, mock_size, video_file):
        info = MagicMock()
        info.gps = [_gps_point()]
        info.make = "BlackVue"
        info.model = "B"
        mock_extract.return_value = info
        result = native.BlackVueVideoExtractor(video_file).extract()
        assert result.filetype == types.FileType.BLACKVUE


class TestNativeVideoExtractor:
    def test_gopro_success(self, video_file):
        expected = MagicMock(spec=types.VideoMetadata)
        with patch.object(native.GoProVideoExtractor, "extract", return_value=expected):
            result = native.NativeVideoExtractor(video_file).extract()
            assert result is expected

    def test_falls_through_to_camm(self, video_file):
        expected = MagicMock(spec=types.VideoMetadata)
        with (
            patch.object(
                native.GoProVideoExtractor,
                "extract",
                side_effect=exceptions.BankingPlatformVideoGPSNotFoundError("x"),
            ),
            patch.object(native.CAMMVideoExtractor, "extract", return_value=expected),
        ):
            result = native.NativeVideoExtractor(video_file).extract()
            assert result is expected

    def test_falls_through_to_blackvue(self, video_file):
        expected = MagicMock(spec=types.VideoMetadata)
        with (
            patch.object(
                native.GoProVideoExtractor,
                "extract",
                side_effect=exceptions.BankingPlatformVideoGPSNotFoundError("x"),
            ),
            patch.object(
                native.CAMMVideoExtractor,
                "extract",
                side_effect=exceptions.BankingPlatformVideoGPSNotFoundError("x"),
            ),
            patch.object(
                native.BlackVueVideoExtractor, "extract", return_value=expected
            ),
        ):
            result = native.NativeVideoExtractor(video_file).extract()
            assert result is expected

    def test_all_fail_raises(self, video_file):
        err = exceptions.BankingPlatformVideoGPSNotFoundError("x")
        with (
            patch.object(native.GoProVideoExtractor, "extract", side_effect=err),
            patch.object(native.CAMMVideoExtractor, "extract", side_effect=err),
            patch.object(native.BlackVueVideoExtractor, "extract", side_effect=err),
        ):
            with pytest.raises(exceptions.BankingPlatformVideoGPSNotFoundError):
                native.NativeVideoExtractor(video_file).extract()

    def test_box_not_found_becomes_invalid_video(self, video_file):
        with patch.object(
            native.GoProVideoExtractor,
            "extract",
            side_effect=simple_format_parser.BoxNotFoundError("bad"),
        ):
            with pytest.raises(exceptions.BankingPlatformInvalidVideoError):
                native.NativeVideoExtractor(video_file).extract()

    def test_filetype_filter_only_camm(self, video_file):
        expected = MagicMock(spec=types.VideoMetadata)
        with patch.object(native.CAMMVideoExtractor, "extract", return_value=expected):
            result = native.NativeVideoExtractor(
                video_file, filetypes={types.FileType.CAMM}
            ).extract()
            assert result is expected
