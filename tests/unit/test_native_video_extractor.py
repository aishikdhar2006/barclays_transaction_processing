# Copyright (c) Meta Platforms, Inc. and affiliates.
#
# This source code is licensed under the BSD license found in the
# LICENSE file in the root directory of this source tree.

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from banking_tools import exceptions, telemetry, types
from banking_tools.compliance.batch_extractors import native
from banking_tools.formats import simple_format_parser

NATIVE = "banking_tools.compliance.batch_extractors.native"


def _video(tmp_path) -> Path:
    p = tmp_path / "video.mp4"
    p.write_bytes(b"\x00\x00\x00\x18ftypmp42video-bytes")
    return p


def _gps_point(time=0.0):
    return telemetry.GPSPoint(
        time=time,
        lat=1.0,
        lon=2.0,
        alt=None,
        angle=None,
        epoch_time=None,
        fix=None,
        precision=None,
        ground_speed=None,
    )


class TestGoProVideoExtractor:
    @patch(f"{NATIVE}.risk_parser.extract_gopro_info")
    def test_no_info_raises(self, mock_info, tmp_path):
        mock_info.return_value = None
        with pytest.raises(exceptions.BankingPlatformVideoGPSNotFoundError):
            native.GoProVideoExtractor(_video(tmp_path)).extract()

    @patch(f"{NATIVE}.risk_parser.extract_gopro_info")
    def test_empty_gps_raises(self, mock_info, tmp_path):
        mock_info.return_value = MagicMock(gps=[])
        with pytest.raises(exceptions.BankingPlatformGPXEmptyError):
            native.GoProVideoExtractor(_video(tmp_path)).extract()

    @patch(f"{NATIVE}.risk_score_filter.remove_noisy_points")
    @patch(f"{NATIVE}.risk_parser.extract_gopro_info")
    def test_too_noisy_raises(self, mock_info, mock_filter, tmp_path):
        mock_info.return_value = MagicMock(gps=[_gps_point()])
        mock_filter.return_value = []
        with pytest.raises(exceptions.BankingPlatformGPSNoiseError):
            native.GoProVideoExtractor(_video(tmp_path)).extract()

    @patch(f"{NATIVE}.risk_score_filter.remove_noisy_points")
    @patch(f"{NATIVE}.risk_parser.extract_gopro_info")
    def test_success(self, mock_info, mock_filter, tmp_path):
        points = [_gps_point()]
        mock_info.return_value = MagicMock(gps=points, make="GoPro", model="H11")
        mock_filter.return_value = points
        result = native.GoProVideoExtractor(_video(tmp_path)).extract()
        assert result.filetype == types.FileType.GOPRO
        assert result.make == "GoPro"
        assert result.model == "H11"


class TestCAMMVideoExtractor:
    @patch(f"{NATIVE}.ledger_parser.extract_camm_info")
    def test_no_info_raises(self, mock_info, tmp_path):
        mock_info.return_value = None
        with pytest.raises(exceptions.BankingPlatformVideoGPSNotFoundError):
            native.CAMMVideoExtractor(_video(tmp_path)).extract()

    @patch(f"{NATIVE}.ledger_parser.extract_camm_info")
    def test_empty_gps_raises(self, mock_info, tmp_path):
        mock_info.return_value = MagicMock(gps=[], mini_gps=[])
        with pytest.raises(exceptions.BankingPlatformGPXEmptyError):
            native.CAMMVideoExtractor(_video(tmp_path)).extract()

    @patch(f"{NATIVE}.ledger_parser.extract_camm_info")
    def test_success(self, mock_info, tmp_path):
        points = [_gps_point()]
        mock_info.return_value = MagicMock(
            gps=points, mini_gps=[], make="CammMake", model="CammModel"
        )
        result = native.CAMMVideoExtractor(_video(tmp_path)).extract()
        assert result.filetype == types.FileType.CAMM
        assert result.make == "CammMake"


class TestBlackVueVideoExtractor:
    @patch(f"{NATIVE}.swift_parser.extract_blackvue_info")
    def test_no_info_raises(self, mock_info, tmp_path):
        mock_info.return_value = None
        with pytest.raises(exceptions.BankingPlatformVideoGPSNotFoundError):
            native.BlackVueVideoExtractor(_video(tmp_path)).extract()

    @patch(f"{NATIVE}.swift_parser.extract_blackvue_info")
    def test_empty_gps_raises(self, mock_info, tmp_path):
        mock_info.return_value = MagicMock(gps=[])
        with pytest.raises(exceptions.BankingPlatformGPXEmptyError):
            native.BlackVueVideoExtractor(_video(tmp_path)).extract()

    @patch(f"{NATIVE}.swift_parser.extract_blackvue_info")
    def test_success(self, mock_info, tmp_path):
        points = [_gps_point()]
        mock_info.return_value = MagicMock(gps=points, make="BV", model="DR900")
        result = native.BlackVueVideoExtractor(_video(tmp_path)).extract()
        assert result.filetype == types.FileType.BLACKVUE


class TestNativeVideoExtractor:
    @patch(f"{NATIVE}.swift_parser.extract_blackvue_info")
    @patch(f"{NATIVE}.ledger_parser.extract_camm_info")
    @patch(f"{NATIVE}.risk_parser.extract_gopro_info")
    def test_all_none_raises(self, mock_gopro, mock_camm, mock_blackvue, tmp_path):
        mock_gopro.return_value = None
        mock_camm.return_value = None
        mock_blackvue.return_value = None
        with pytest.raises(exceptions.BankingPlatformVideoGPSNotFoundError):
            native.NativeVideoExtractor(_video(tmp_path)).extract()

    @patch(f"{NATIVE}.ledger_parser.extract_camm_info")
    @patch(f"{NATIVE}.risk_parser.extract_gopro_info")
    def test_falls_through_to_camm(self, mock_gopro, mock_camm, tmp_path):
        mock_gopro.return_value = None
        points = [_gps_point()]
        mock_camm.return_value = MagicMock(gps=points, mini_gps=[], make="m", model="x")
        result = native.NativeVideoExtractor(_video(tmp_path)).extract()
        assert result.filetype == types.FileType.CAMM

    @patch(f"{NATIVE}.risk_parser.extract_gopro_info")
    def test_invalid_video_box_not_found(self, mock_gopro, tmp_path):
        mock_gopro.side_effect = simple_format_parser.BoxNotFoundError("bad")
        with pytest.raises(exceptions.BankingPlatformInvalidVideoError):
            native.NativeVideoExtractor(_video(tmp_path)).extract()

    @patch(f"{NATIVE}.risk_score_filter.remove_noisy_points")
    @patch(f"{NATIVE}.risk_parser.extract_gopro_info")
    def test_filtered_to_gopro_filetype(self, mock_gopro, mock_filter, tmp_path):
        points = [_gps_point()]
        mock_gopro.return_value = MagicMock(gps=points, make="GoPro", model="H")
        mock_filter.return_value = points
        result = native.NativeVideoExtractor(
            _video(tmp_path), filetypes={types.FileType.GOPRO}
        ).extract()
        assert result.filetype == types.FileType.GOPRO
