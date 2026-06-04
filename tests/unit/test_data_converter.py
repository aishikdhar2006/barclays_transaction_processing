# Copyright (c) Meta Platforms, Inc. and affiliates.
#
# This source code is licensed under the BSD license found in the
# LICENSE file in the root directory of this source tree.

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from banking_tools import data_converter


class TestTruncateBegin:
    def test_short_string(self):
        assert data_converter._truncate_begin("hello") == "hello"

    def test_long_string(self):
        long_str = "x" * 3000
        result = data_converter._truncate_begin(long_str)
        assert result.startswith("...")
        assert len(result) == data_converter._MAX_STDERR_LENGTH + 3


class TestTruncateEnd:
    def test_short_string(self):
        assert data_converter._truncate_end("hello") == "hello"

    def test_long_string(self):
        long_str = "x" * 3000
        result = data_converter._truncate_end(long_str)
        assert result.endswith("...")
        assert len(result) == data_converter._MAX_STDERR_LENGTH + 3


class TestFFmpegCalledProcessError:
    def test_str_with_stderr(self):
        inner = subprocess.CalledProcessError(1, "ffmpeg")
        inner.stderr = b"some error output"
        ex = data_converter.FFmpegCalledProcessError(inner)
        result = str(ex)
        assert "some error output" in result
        assert "STDERR:" in result

    def test_str_without_stderr(self):
        inner = subprocess.CalledProcessError(1, "ffmpeg")
        inner.stderr = None
        ex = data_converter.FFmpegCalledProcessError(inner)
        result = str(ex)
        assert "STDERR:" not in result

    def test_str_with_binary_stderr(self):
        inner = subprocess.CalledProcessError(1, "ffmpeg")
        inner.stderr = b"\xff\xfe invalid utf8"
        ex = data_converter.FFmpegCalledProcessError(inner)
        # Should not raise
        str(ex)


class TestFFmpegInit:
    def test_default_paths(self):
        ff = data_converter.FFMPEG()
        assert ff.data_converter_path == "ffmpeg"
        assert ff.ffprobe_path == "ffprobe"
        assert ff.stderr is None

    def test_custom_paths(self):
        ff = data_converter.FFMPEG(
            data_converter_path="/usr/bin/ffmpeg",
            ffprobe_path="/usr/bin/ffprobe",
            stderr=subprocess.PIPE,
        )
        assert ff.data_converter_path == "/usr/bin/ffmpeg"
        assert ff.ffprobe_path == "/usr/bin/ffprobe"


class TestFFmpegNotFoundError:
    def test_creation(self):
        ex = data_converter.FFmpegNotFoundError("ffmpeg not found")
        assert str(ex) == "ffmpeg not found"


class TestProbeOutput:
    def test_stream_tag_fields(self):
        tag: data_converter.StreamTag = {"creation_time": "2023", "language": "eng"}
        assert tag["creation_time"] == "2023"

    def test_stream_fields(self):
        stream: data_converter.Stream = {
            "codec_name": "h264",
            "codec_tag_string": "avc1",
            "codec_type": "video",
            "duration": "10.0",
            "height": 1080,
            "index": 0,
            "tags": {"creation_time": "2023", "language": "eng"},
            "width": 1920,
            "r_frame_rate": "30/1",
            "avg_frame_rate": "30/1",
            "nb_frames": "300",
        }
        assert stream["codec_name"] == "h264"


class TestGenerateBinarySearch:
    def test_empty(self):
        assert data_converter.FFMPEG.generate_binary_search([]) == "0"

    def test_single(self):
        result = data_converter.FFMPEG.generate_binary_search([1])
        assert result == "eq(n\\,1)"

    def test_two_elements(self):
        result = data_converter.FFMPEG.generate_binary_search([1, 2])
        assert "if(lt(n\\,2)" in result
        assert "eq(n\\,1)" in result
        assert "eq(n\\,2)" in result

    def test_three_elements(self):
        result = data_converter.FFMPEG.generate_binary_search([1, 2, 3])
        assert "eq(n\\,1)" in result
        assert "eq(n\\,2)" in result
        assert "eq(n\\,3)" in result


class TestValidateStreamSpecifier:
    def test_valid_v(self):
        data_converter.FFMPEG._validate_stream_specifier("v")

    def test_valid_integer(self):
        data_converter.FFMPEG._validate_stream_specifier(0)

    def test_valid_string_integer(self):
        data_converter.FFMPEG._validate_stream_specifier("1")

    def test_invalid_string(self):
        with pytest.raises(ValueError, match="Invalid stream specifier"):
            data_converter.FFMPEG._validate_stream_specifier("invalid")


class TestExtractStreamFrameIdx:
    def test_valid_v_frame(self):
        import re

        pattern = re.compile(
            r"^test_(?P<stream_specifier>\d+|v)_(?P<frame_idx>\d+)$", re.X
        )
        result = data_converter.FFMPEG._extract_stream_frame_idx(
            "test_v_000001.jpg", pattern
        )
        assert result == ("v", 1)

    def test_valid_numbered_stream(self):
        import re

        pattern = re.compile(
            r"^test_(?P<stream_specifier>\d+|v)_(?P<frame_idx>\d+)$", re.X
        )
        result = data_converter.FFMPEG._extract_stream_frame_idx(
            "test_1_000002.jpg", pattern
        )
        assert result == ("1", 2)

    def test_wrong_extension(self):
        import re

        pattern = re.compile(
            r"^test_(?P<stream_specifier>\d+|v)_(?P<frame_idx>\d+)$", re.X
        )
        result = data_converter.FFMPEG._extract_stream_frame_idx(
            "test_v_000001.png", pattern
        )
        assert result is None

    def test_no_match(self):
        import re

        pattern = re.compile(
            r"^test_(?P<stream_specifier>\d+|v)_(?P<frame_idx>\d+)$", re.X
        )
        result = data_converter.FFMPEG._extract_stream_frame_idx(
            "other_file.jpg", pattern
        )
        assert result is None


class TestIterateSamples:
    def test_finds_samples(self, tmp_path):
        from pathlib import Path

        # Create sample files matching the expected pattern
        video_path = Path("test_video.mp4")
        (tmp_path / "test_video_v_000001.jpg").touch()
        (tmp_path / "test_video_v_000002.jpg").touch()
        (tmp_path / "random_file.txt").touch()
        results = list(data_converter.FFMPEG.iterate_samples(tmp_path, video_path))
        assert len(results) == 2

    def test_empty_dir(self, tmp_path):
        from pathlib import Path

        video_path = Path("test_video.mp4")
        results = list(data_converter.FFMPEG.iterate_samples(tmp_path, video_path))
        assert results == []


class TestSortSelectedSamples:
    def test_single_stream(self, tmp_path):
        from pathlib import Path

        video_path = Path("test_video.mp4")
        (tmp_path / "test_video_v_000001.jpg").touch()
        (tmp_path / "test_video_v_000002.jpg").touch()
        results = data_converter.FFMPEG.sort_selected_samples(tmp_path, video_path)
        assert len(results) == 2
        assert results[0][0] == 1
        assert results[1][0] == 2


class TestProbe:
    def test_probe_video_streams(self):
        probe_output = {
            "streams": [
                {"codec_type": "video", "width": 1920, "height": 1080},
                {"codec_type": "audio"},
                {"codec_type": "video", "width": 640, "height": 480},
            ]
        }
        probe = data_converter.Probe(probe_output)
        video_streams = probe.probe_video_streams()
        assert len(video_streams) == 2

    def test_probe_video_with_max_resolution(self):
        probe_output = {
            "streams": [
                {"codec_type": "video", "width": 640, "height": 480},
                {"codec_type": "video", "width": 1920, "height": 1080},
            ]
        }
        probe = data_converter.Probe(probe_output)
        result = probe.probe_video_with_max_resolution()
        assert result["width"] == 1920

    def test_probe_video_with_max_resolution_empty(self):
        probe_output = {"streams": []}
        probe = data_converter.Probe(probe_output)
        result = probe.probe_video_with_max_resolution()
        assert result is None

    def test_extract_stream_start_time(self):
        stream = {
            "duration": "10.0",
            "tags": {"creation_time": "2023-06-15T12:00:00+00:00"},
        }
        result = data_converter.Probe.extract_stream_start_time(stream)
        assert result is not None
        assert result.year == 2023

    def test_extract_stream_start_time_no_duration(self):
        stream = {"tags": {"creation_time": "2023-06-15T12:00:00+00:00"}}
        result = data_converter.Probe.extract_stream_start_time(stream)
        assert result is None

    def test_extract_stream_start_time_no_creation_time(self):
        stream = {"duration": "10.0", "tags": {}}
        result = data_converter.Probe.extract_stream_start_time(stream)
        assert result is None

    def test_probe_video_start_time(self):
        probe_output = {
            "streams": [
                {
                    "codec_type": "video",
                    "width": 1920,
                    "height": 1080,
                    "duration": "60.0",
                    "tags": {"creation_time": "2023-06-15T12:01:00+00:00"},
                }
            ]
        }
        probe = data_converter.Probe(probe_output)
        result = probe.probe_video_start_time()
        assert result is not None

    def test_probe_video_start_time_no_streams(self):
        probe_output = {"streams": []}
        probe = data_converter.Probe(probe_output)
        result = probe.probe_video_start_time()
        assert result is None


class TestRunDataConverterNonInteractive:
    @patch("subprocess.run")
    def test_file_not_found(self, mock_run):
        mock_run.side_effect = FileNotFoundError()
        ff = data_converter.FFMPEG()
        with pytest.raises(data_converter.FFmpegNotFoundError):
            ff.run_data_converter_non_interactive(["-version"])

    @patch("subprocess.run")
    def test_called_process_error(self, mock_run):
        mock_run.side_effect = subprocess.CalledProcessError(
            1, "ffmpeg", stderr=b"error"
        )
        ff = data_converter.FFMPEG()
        with pytest.raises(data_converter.FFmpegCalledProcessError):
            ff.run_data_converter_non_interactive(["-version"])

    @patch("subprocess.run")
    def test_success(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        ff = data_converter.FFMPEG()
        ff.run_data_converter_non_interactive(["-version"])
        mock_run.assert_called_once()


class TestRunFfprobeJson:
    @patch("subprocess.run")
    def test_file_not_found(self, mock_run):
        mock_run.side_effect = FileNotFoundError()
        ff = data_converter.FFMPEG()
        with pytest.raises(data_converter.FFmpegNotFoundError):
            ff._run_ffprobe_json(["-show_streams", "test.mp4"])

    @patch("subprocess.run")
    def test_success(self, mock_run):
        import json

        mock_run.return_value = MagicMock(
            stdout=json.dumps({"streams": []}).encode("utf-8"),
            returncode=0,
        )
        ff = data_converter.FFMPEG()
        result = ff._run_ffprobe_json(["-show_streams", "test.mp4"])
        assert result == {"streams": []}

    @patch("subprocess.run")
    def test_empty_output(self, mock_run):
        import json

        mock_run.return_value = MagicMock(
            stdout=json.dumps({}).encode("utf-8"),
            stderr=b"some error",
            returncode=0,
        )
        ff = data_converter.FFMPEG()
        with pytest.raises(RuntimeError, match="Empty JSON"):
            ff._run_ffprobe_json(["-show_streams", "test.mp4"])

    @patch("subprocess.run")
    def test_invalid_json(self, mock_run):
        mock_run.return_value = MagicMock(
            stdout=b"not json",
            returncode=0,
        )
        ff = data_converter.FFMPEG()
        with pytest.raises(RuntimeError, match="Error JSON decoding"):
            ff._run_ffprobe_json(["-show_streams", "test.mp4"])
