# Copyright (c) Meta Platforms, Inc. and affiliates.
#
# This source code is licensed under the BSD license found in the
# LICENSE file in the root directory of this source tree.

from unittest.mock import MagicMock, patch

import pytest

from banking_tools import exceptions, sample_transactions


class TestNormalizePath:
    def test_directory_with_videos(self, tmp_path):
        # Create a dummy video file
        vid = tmp_path / "test.mp4"
        vid.touch()
        video_dir, video_list = sample_transactions._normalize_path(
            tmp_path, skip_subfolders=False
        )
        assert video_dir == tmp_path.resolve()

    def test_single_file(self, tmp_path):
        vid = tmp_path / "test.mp4"
        vid.touch()
        video_dir, video_list = sample_transactions._normalize_path(
            vid, skip_subfolders=False
        )
        assert video_dir == tmp_path.resolve()
        assert video_list == [vid]

    def test_nonexistent_raises(self, tmp_path):
        fake = tmp_path / "nonexistent"
        with pytest.raises(exceptions.BankingPlatformFileNotFoundError):
            sample_transactions._normalize_path(fake, skip_subfolders=False)


class TestXor:
    def test_true_false(self):
        assert sample_transactions.xor(True, False) is True

    def test_false_true(self):
        assert sample_transactions.xor(False, True) is True

    def test_true_true(self):
        assert sample_transactions.xor(True, True) is False

    def test_false_false(self):
        assert sample_transactions.xor(False, False) is False


class TestWipDirContext:
    def test_normal_flow(self, tmp_path):
        wip = tmp_path / "wip"
        done = tmp_path / "done"

        with sample_transactions.wip_dir_context(wip, done) as d:
            assert d == wip
            assert wip.is_dir()
            (wip / "test.txt").write_text("hello")

        assert done.is_dir()
        assert (done / "test.txt").read_text() == "hello"
        assert not wip.exists()

    def test_exception_cleans_wip(self, tmp_path):
        wip = tmp_path / "wip"
        done = tmp_path / "done"

        with pytest.raises(RuntimeError):
            with sample_transactions.wip_dir_context(wip, done):
                raise RuntimeError("test error")

        assert not wip.exists()
        assert not done.exists()


class TestSampleTransactions:
    def test_invalid_params_raises(self, tmp_path):
        vid = tmp_path / "test.mp4"
        vid.touch()
        with pytest.raises(exceptions.BankingPlatformBadParameterError):
            sample_transactions.sample_transactions(
                video_import_path=tmp_path,
                import_path=tmp_path / "output",
                video_sample_distance=-1,
                video_sample_interval=-1,
            )

    def test_invalid_start_time_raises(self, tmp_path):
        vid = tmp_path / "test.mp4"
        vid.touch()
        with pytest.raises(exceptions.BankingPlatformBadParameterError):
            sample_transactions.sample_transactions(
                video_import_path=tmp_path,
                import_path=tmp_path / "output",
                video_start_time="not_a_date",
            )


class TestWipSampleDir:
    def test_prefix_and_parent(self, tmp_path):
        sample_dir = tmp_path / "out" / "video.mp4"
        result = sample_transactions.wip_sample_dir(sample_dir)
        assert result.parent == sample_dir.resolve().parent
        assert result.name.startswith(".mly_data_converter_video.mp4_")


class TestWithinTrackTimeRangeBuffered:
    def _pt(self, t):
        p = MagicMock()
        p.time = t
        return p

    def test_within_range(self):
        points = [self._pt(0.0), self._pt(10.0)]
        assert (
            sample_transactions._within_track_time_range_buffered(points, 5.0) is True
        )

    def test_at_buffered_edge(self):
        points = [self._pt(0.0), self._pt(10.0)]
        assert (
            sample_transactions._within_track_time_range_buffered(points, 10.0005)
            is True
        )

    def test_outside_range(self):
        points = [self._pt(0.0), self._pt(10.0)]
        assert (
            sample_transactions._within_track_time_range_buffered(points, 20.0) is False
        )


class TestSampleTransactionsOrchestration:
    @patch.object(sample_transactions, "_sample_single_video_by_distance")
    def test_distance_branch_called(self, mock_distance, tmp_path):
        vid = tmp_path / "v.mp4"
        vid.touch()
        out = tmp_path / "out"
        sample_transactions.sample_transactions(
            video_import_path=vid,
            import_path=out,
            video_sample_distance=5,
            video_sample_interval=0,
        )
        mock_distance.assert_called_once()

    @patch.object(sample_transactions, "_sample_single_video_by_interval")
    def test_interval_branch_called(self, mock_interval, tmp_path):
        vid = tmp_path / "v.mp4"
        vid.touch()
        out = tmp_path / "out"
        sample_transactions.sample_transactions(
            video_import_path=vid,
            import_path=out,
            video_sample_distance=-1,
            video_sample_interval=2,
        )
        mock_interval.assert_called_once()

    @patch.object(sample_transactions, "_sample_single_video_by_distance")
    def test_skip_existing_sample_dir(self, mock_distance, tmp_path):
        vid = tmp_path / "v.mp4"
        vid.touch()
        out = tmp_path / "out"
        # Pre-create the sample dir so it is skipped
        sample_dir = out / "v.mp4"
        sample_dir.mkdir(parents=True)
        sample_transactions.sample_transactions(
            video_import_path=vid,
            import_path=out,
            video_sample_distance=5,
            video_sample_interval=0,
        )
        mock_distance.assert_not_called()

    @patch.object(sample_transactions, "_sample_single_video_by_distance")
    def test_rerun_removes_existing(self, mock_distance, tmp_path):
        vid = tmp_path / "v.mp4"
        vid.touch()
        out = tmp_path / "out"
        sample_dir = out / "v.mp4"
        sample_dir.mkdir(parents=True)
        (sample_dir / "old.jpg").write_text("x")
        sample_transactions.sample_transactions(
            video_import_path=vid,
            import_path=out,
            video_sample_distance=5,
            video_sample_interval=0,
            rerun=True,
        )
        mock_distance.assert_called_once()

    @patch.object(sample_transactions, "_sample_single_video_by_distance")
    def test_ffmpeg_not_found_raises(self, mock_distance, tmp_path):
        from banking_tools import data_converter as dc

        mock_distance.side_effect = dc.FFmpegNotFoundError("no ffmpeg")
        vid = tmp_path / "v.mp4"
        vid.touch()
        with pytest.raises(exceptions.BankingPlatformFFmpegNotFoundError):
            sample_transactions.sample_transactions(
                video_import_path=vid,
                import_path=tmp_path / "out",
                video_sample_distance=5,
                video_sample_interval=0,
            )

    @patch.object(sample_transactions, "_sample_single_video_by_distance")
    def test_skip_sample_errors(self, mock_distance, tmp_path):
        mock_distance.side_effect = ValueError("boom")
        vid = tmp_path / "v.mp4"
        vid.touch()
        # Should not raise because skip_sample_errors=True
        sample_transactions.sample_transactions(
            video_import_path=vid,
            import_path=tmp_path / "out",
            video_sample_distance=5,
            video_sample_interval=0,
            skip_sample_errors=True,
        )

    @patch.object(sample_transactions, "_sample_single_video_by_distance")
    def test_error_propagates_without_skip(self, mock_distance, tmp_path):
        mock_distance.side_effect = ValueError("boom")
        vid = tmp_path / "v.mp4"
        vid.touch()
        with pytest.raises(ValueError):
            sample_transactions.sample_transactions(
                video_import_path=vid,
                import_path=tmp_path / "out",
                video_sample_distance=5,
                video_sample_interval=0,
                skip_sample_errors=False,
            )


class TestSampleSingleVideoByInterval:
    @patch.object(sample_transactions, "ExifEdit")
    @patch.object(sample_transactions, "wip_dir_context")
    @patch.object(sample_transactions.data_converterlib, "FFMPEG")
    def test_extracts_and_writes(self, mock_ffmpeg_cls, mock_wip, mock_exif, tmp_path):
        import datetime

        data_converter = MagicMock()
        mock_ffmpeg_cls.return_value = data_converter
        wip = tmp_path / "wip"
        wip.mkdir()
        mock_wip.return_value.__enter__ = MagicMock(return_value=wip)
        mock_wip.return_value.__exit__ = MagicMock(return_value=False)

        sample_path = tmp_path / "frame.jpg"
        sample_path.touch()
        mock_ffmpeg_cls.sort_selected_samples.return_value = [
            (1, [sample_path]),
            (2, [None]),
        ]

        start = datetime.datetime(2023, 1, 1, tzinfo=datetime.timezone.utc)
        sample_transactions._sample_single_video_by_interval(
            tmp_path / "v.mp4",
            tmp_path / "out",
            sample_interval=1.0,
            duration_ratio=1.0,
            start_time=start,
        )
        data_converter.extract_frames_by_interval.assert_called_once()
        mock_exif.assert_called_once_with(sample_path)
        mock_exif.return_value.write.assert_called_once()

    @patch.object(sample_transactions.data_converterlib, "Probe")
    @patch.object(sample_transactions.data_converterlib, "FFMPEG")
    def test_no_start_time_unextractable_raises(
        self, mock_ffmpeg_cls, mock_probe_cls, tmp_path
    ):
        mock_ffmpeg_cls.return_value = MagicMock()
        mock_probe_cls.return_value.probe_video_start_time.return_value = None
        with pytest.raises(exceptions.BankingPlatformVideoError):
            sample_transactions._sample_single_video_by_interval(
                tmp_path / "v.mp4",
                tmp_path / "out",
                sample_interval=1.0,
                duration_ratio=1.0,
                start_time=None,
            )


class TestSampleStreamByDistance:
    @patch.object(sample_transactions.currency, "sample_points_by_distance")
    @patch.object(sample_transactions.currency, "Interpolator")
    def test_builds_index(self, mock_interp_cls, mock_select):

        def _pt(t):
            p = MagicMock()
            p.time = t
            return p

        points = [_pt(0.0), _pt(10.0)]

        def _sample(t):
            s = MagicMock()
            s.exact_composition_time = t
            return s

        samples = [_sample(1.0), _sample(2.0)]
        track_parser = MagicMock()
        track_parser.extract_samples.return_value = samples

        interp = MagicMock()
        mock_interp_cls.return_value.interpolate.return_value = interp

        # sample_points_by_distance returns selected items unchanged
        mock_select.return_value = [
            (0, samples[0], interp),
            (1, samples[1], interp),
        ]

        result = sample_transactions._sample_transactions_stream_by_distance(
            points, track_parser, sample_distance=1.0
        )
        assert set(result.keys()) == {0, 1}
        assert result[0][0] is samples[0]


class TestSampleSingleVideoByDistance:
    @patch.object(sample_transactions, "ExifEdit")
    @patch.object(sample_transactions, "wip_dir_context")
    @patch.object(sample_transactions, "_sample_transactions_stream_by_distance")
    @patch.object(sample_transactions.format_sample_parser, "MovieBoxParser")
    @patch.object(
        sample_transactions.validate_batches_from_batch, "GeotagVideosFromVideo"
    )
    @patch.object(sample_transactions.data_converterlib, "Probe")
    @patch.object(sample_transactions.data_converterlib, "FFMPEG")
    def test_full_flow_writes_exif(
        self,
        mock_ffmpeg_cls,
        mock_probe_cls,
        mock_geotag_cls,
        mock_moov_cls,
        mock_stream,
        mock_wip,
        mock_exif,
        tmp_path,
    ):
        import datetime

        data_converter = MagicMock()
        mock_ffmpeg_cls.return_value = data_converter

        probe = MagicMock()
        probe.probe_video_with_max_resolution.return_value = {"index": 0}
        mock_probe_cls.return_value = probe

        video_metadata = MagicMock()
        video_metadata.points = [MagicMock()]
        video_metadata.make = "GoPro"
        video_metadata.model = "Hero"
        # Make isinstance(video_metadata, ErrorMetadata) False
        mock_geotag_cls.return_value.to_description.return_value = [video_metadata]

        video_sample = MagicMock()
        video_sample.exact_composition_time = 5.0
        interp = MagicMock()
        interp.time = 5.0
        interp.get_gps_epoch_time.return_value = None
        interp.lat = 40.0
        interp.lon = -74.0
        interp.alt = 100.0
        interp.angle = 90.0
        mock_stream.return_value = {0: (video_sample, interp)}

        wip = tmp_path / "wip"
        wip.mkdir()
        mock_wip.return_value.__enter__ = MagicMock(return_value=wip)
        mock_wip.return_value.__exit__ = MagicMock(return_value=False)

        sample_path = tmp_path / "frame.jpg"
        sample_path.touch()
        mock_ffmpeg_cls.sort_selected_samples.return_value = [(1, [sample_path])]

        start = datetime.datetime(2023, 1, 1, tzinfo=datetime.timezone.utc)
        sample_transactions._sample_single_video_by_distance(
            tmp_path / "v.mp4",
            tmp_path / "out",
            sample_distance=5.0,
            start_time=start,
        )
        mock_exif.assert_called_once_with(sample_path)
        mock_exif.return_value.add_lat_lon.assert_called_once_with(40.0, -74.0)
        mock_exif.return_value.write.assert_called_once()

    @patch.object(
        sample_transactions.validate_batches_from_batch, "GeotagVideosFromVideo"
    )
    @patch.object(sample_transactions.data_converterlib, "Probe")
    @patch.object(sample_transactions.data_converterlib, "FFMPEG")
    def test_error_metadata_returns_early(
        self, mock_ffmpeg_cls, mock_probe_cls, mock_geotag_cls, tmp_path
    ):
        import datetime

        from banking_tools import types

        mock_ffmpeg_cls.return_value = MagicMock()
        mock_probe_cls.return_value = MagicMock()
        err = MagicMock(spec=types.ErrorMetadata)
        err.error = "bad video"
        mock_geotag_cls.return_value.to_description.return_value = [err]

        # Should return without raising
        sample_transactions._sample_single_video_by_distance(
            tmp_path / "v.mp4",
            tmp_path / "out",
            sample_distance=5.0,
            start_time=datetime.datetime(2023, 1, 1, tzinfo=datetime.timezone.utc),
        )
