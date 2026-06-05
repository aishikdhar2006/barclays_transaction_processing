# Copyright (c) Meta Platforms, Inc. and affiliates.
#
# This source code is licensed under the BSD license found in the
# LICENSE file in the root directory of this source tree.

from pathlib import Path
from unittest.mock import patch

import pytest

from banking_tools import currency, exceptions, telemetry, types
from banking_tools.compliance.batch_extractors.audit import (
    GPXVideoExtractor,
    SyncMode,
)


def _point(time, lat=1.0, lon=2.0):
    return currency.Point(time=time, lat=lat, lon=lon, alt=None, angle=None)


def _gps_point(time, epoch_time=None):
    return telemetry.GPSPoint(
        time=time,
        lat=1.0,
        lon=2.0,
        alt=None,
        angle=None,
        epoch_time=epoch_time,
        fix=None,
        precision=None,
        ground_speed=None,
    )


def _video(tmp_path) -> Path:
    p = tmp_path / "video.mp4"
    p.write_bytes(b"\x00\x00\x00\x18ftypmp42video-bytes")
    return p


class TestRebaseTimes:
    def test_rebase_to_zero(self):
        pts = [_point(10), _point(12), _point(15)]
        GPXVideoExtractor._rebase_times(pts)
        assert [p.time for p in pts] == [0.0, 2.0, 5.0]

    def test_rebase_with_offset(self):
        pts = [_point(10), _point(12)]
        GPXVideoExtractor._rebase_times(pts, offset=100.0)
        assert [p.time for p in pts] == [100.0, 102.0]

    def test_rebase_empty_noop(self):
        GPXVideoExtractor._rebase_times([])


class TestGpxOffset:
    def test_empty_returns_zero(self):
        assert GPXVideoExtractor._gpx_offset([], [_point(1)]) == 0.0
        assert GPXVideoExtractor._gpx_offset([_point(1)], []) == 0.0

    def test_plain_points_zero_offset(self):
        gpx = [_point(5)]
        assert GPXVideoExtractor._gpx_offset(gpx, [_point(3)]) == 0.0

    def test_gps_epoch_offset(self):
        gpx = [_point(100)]
        video = [_gps_point(0, epoch_time=40)]
        assert GPXVideoExtractor._gpx_offset(gpx, video) == 60.0


class TestExtract:
    @patch("banking_tools.compliance.batch_extractors.audit.parse_gpx")
    @patch("banking_tools.compliance.batch_extractors.audit.NativeVideoExtractor")
    def test_gps_not_found_sync_falls_back_to_rebase(
        self, mock_native, mock_parse, tmp_path
    ):
        video = _video(tmp_path)
        mock_parse.return_value = [[_point(10), _point(13)]]
        mock_native.return_value.extract.side_effect = (
            exceptions.BankingPlatformVideoGPSNotFoundError("no gps")
        )

        extractor = GPXVideoExtractor(video, tmp_path / "t.gpx", SyncMode.SYNC)
        result = extractor.extract()
        assert isinstance(result, types.VideoMetadata)
        assert [p.time for p in result.points] == [0.0, 3.0]

    @patch("banking_tools.compliance.batch_extractors.audit.parse_gpx")
    @patch("banking_tools.compliance.batch_extractors.audit.NativeVideoExtractor")
    def test_gps_not_found_strict_raises(self, mock_native, mock_parse, tmp_path):
        video = _video(tmp_path)
        mock_parse.return_value = [[_point(10)]]
        mock_native.return_value.extract.side_effect = (
            exceptions.BankingPlatformVideoGPSNotFoundError("no gps")
        )

        extractor = GPXVideoExtractor(video, tmp_path / "t.gpx", SyncMode.STRICT_SYNC)
        with pytest.raises(exceptions.BankingPlatformVideoGPSNotFoundError):
            extractor.extract()

    @patch("banking_tools.compliance.batch_extractors.audit.parse_gpx")
    @patch("banking_tools.compliance.batch_extractors.audit.NativeVideoExtractor")
    def test_native_success_rebase(self, mock_native, mock_parse, tmp_path):
        video = _video(tmp_path)
        mock_parse.return_value = [[_point(20), _point(25)]]
        native_md = types.VideoMetadata(
            filename=video,
            filetype=types.FileType.VIDEO,
            points=[_gps_point(0, epoch_time=1000)],
        )
        mock_native.return_value.extract.return_value = native_md

        extractor = GPXVideoExtractor(video, tmp_path / "t.gpx", SyncMode.REBASE)
        result = extractor.extract()
        assert [p.time for p in result.points] == [0.0, 5.0]

    @patch("banking_tools.compliance.batch_extractors.audit.parse_gpx")
    @patch("banking_tools.compliance.batch_extractors.audit.NativeVideoExtractor")
    def test_native_success_sync_offset(self, mock_native, mock_parse, tmp_path):
        video = _video(tmp_path)
        mock_parse.return_value = [[_point(100), _point(105)]]
        native_md = types.VideoMetadata(
            filename=video,
            filetype=types.FileType.VIDEO,
            points=[_gps_point(0, epoch_time=40)],
        )
        mock_native.return_value.extract.return_value = native_md

        extractor = GPXVideoExtractor(video, tmp_path / "t.gpx", SyncMode.SYNC)
        result = extractor.extract()
        # offset = 100 - 40 = 60; rebased: (t - 100) + 60
        assert [p.time for p in result.points] == [60.0, 65.0]
