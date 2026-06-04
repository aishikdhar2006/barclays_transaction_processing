# Copyright (c) Meta Platforms, Inc. and affiliates.
#
# This source code is licensed under the BSD license found in the
# LICENSE file in the root directory of this source tree.

from unittest.mock import MagicMock, patch

import pytest

from banking_tools import currency, exceptions, types
from banking_tools.compliance.batch_extractors import audit
from banking_tools.compliance.batch_extractors.audit import GPXVideoExtractor, SyncMode


def _pt(time, lat=1.0, lon=2.0):
    return currency.Point(time=time, lat=lat, lon=lon, alt=None, angle=None)


@pytest.fixture
def paths(tmp_path):
    video = tmp_path / "video.mp4"
    video.write_bytes(b"data")
    gpx = tmp_path / "track.gpx"
    gpx.write_text("<gpx></gpx>")
    return video, gpx


class TestRebaseTimes:
    def test_rebase_to_zero(self):
        points = [_pt(10), _pt(15), _pt(20)]
        GPXVideoExtractor._rebase_times(points)
        assert [p.time for p in points] == [0.0, 5.0, 10.0]

    def test_rebase_with_offset(self):
        points = [_pt(10), _pt(20)]
        GPXVideoExtractor._rebase_times(points, offset=100.0)
        assert [p.time for p in points] == [100.0, 110.0]

    def test_rebase_empty(self):
        GPXVideoExtractor._rebase_times([])  # no error


class TestGpxOffset:
    def test_empty_returns_zero(self):
        assert GPXVideoExtractor._gpx_offset([], [_pt(1)]) == 0.0
        assert GPXVideoExtractor._gpx_offset([_pt(1)], []) == 0.0

    def test_no_epoch_time_returns_zero(self):
        assert GPXVideoExtractor._gpx_offset([_pt(5)], [_pt(3)]) == 0.0

    def test_gps_point_epoch_time(self):
        gps_point = MagicMock(spec=audit.telemetry.GPSPoint)
        gps_point.epoch_time = 3.0
        offset = GPXVideoExtractor._gpx_offset([_pt(5)], [gps_point])
        assert offset == 2.0


class TestExtract:
    def test_no_video_gps_non_strict_uses_gpx(self, paths):
        video, gpx = paths
        with (
            patch.object(audit, "parse_gpx", return_value=[[_pt(10), _pt(20)]]),
            patch.object(audit, "get_file_size", create=True, return_value=5),
            patch.object(
                audit.NativeVideoExtractor,
                "extract",
                side_effect=exceptions.BankingPlatformVideoGPSNotFoundError("x"),
            ),
            patch.object(audit.utils, "get_file_size", return_value=5),
        ):
            ext = GPXVideoExtractor(video, gpx, sync_mode=SyncMode.SYNC)
            result = ext.extract()
            assert result.filetype == types.FileType.VIDEO
            assert result.points[0].time == 0.0

    def test_no_video_gps_strict_raises(self, paths):
        video, gpx = paths
        with (
            patch.object(audit, "parse_gpx", return_value=[[_pt(10)]]),
            patch.object(
                audit.NativeVideoExtractor,
                "extract",
                side_effect=exceptions.BankingPlatformVideoGPSNotFoundError("x"),
            ),
        ):
            ext = GPXVideoExtractor(video, gpx, sync_mode=SyncMode.STRICT_SYNC)
            with pytest.raises(exceptions.BankingPlatformVideoGPSNotFoundError):
                ext.extract()

    def test_rebase_mode(self, paths):
        video, gpx = paths
        native_md = types.VideoMetadata(
            filename=video,
            filesize=5,
            filetype=types.FileType.GOPRO,
            points=[_pt(100)],
        )
        with (
            patch.object(audit, "parse_gpx", return_value=[[_pt(10), _pt(20)]]),
            patch.object(audit.NativeVideoExtractor, "extract", return_value=native_md),
        ):
            ext = GPXVideoExtractor(video, gpx, sync_mode=SyncMode.REBASE)
            result = ext.extract()
            assert result.points[0].time == 0.0

    def test_sync_mode_applies_offset(self, paths):
        video, gpx = paths
        native_md = types.VideoMetadata(
            filename=video,
            filesize=5,
            filetype=types.FileType.GOPRO,
            points=[_pt(100)],
        )
        with (
            patch.object(audit, "parse_gpx", return_value=[[_pt(10)]]),
            patch.object(audit.NativeVideoExtractor, "extract", return_value=native_md),
        ):
            ext = GPXVideoExtractor(video, gpx, sync_mode=SyncMode.SYNC)
            result = ext.extract()
            assert result.filetype == types.FileType.GOPRO

    def test_multiple_tracks_merged(self, paths):
        video, gpx = paths
        native_md = types.VideoMetadata(
            filename=video,
            filesize=5,
            filetype=types.FileType.GOPRO,
            points=[_pt(100)],
        )
        with (
            patch.object(audit, "parse_gpx", return_value=[[_pt(10)], [_pt(20)]]),
            patch.object(audit.NativeVideoExtractor, "extract", return_value=native_md),
        ):
            ext = GPXVideoExtractor(video, gpx, sync_mode=SyncMode.REBASE)
            result = ext.extract()
            assert len(result.points) == 2
