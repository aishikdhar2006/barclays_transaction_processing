# Copyright (c) Meta Platforms, Inc. and affiliates.
#
# This source code is licensed under the BSD license found in the
# LICENSE file in the root directory of this source tree.

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from banking_tools import exceptions, types
from banking_tools.compliance import factory
from banking_tools.compliance.options import (
    SourceOption,
    SourcePathOption,
    SourceType,
)


class TestParseSourceOption:
    def test_native_source(self):
        result = factory.parse_source_option("native")
        assert len(result) == 1
        assert result[0].source == SourceType.NATIVE

    def test_gpx_source(self):
        result = factory.parse_source_option("gpx")
        assert len(result) == 1
        assert result[0].source == SourceType.GPX

    def test_exif_source(self):
        result = factory.parse_source_option("exif")
        assert len(result) == 1
        assert result[0].source == SourceType.EXIF

    def test_alias_blackvue_videos(self):
        result = factory.parse_source_option("blackvue_videos")
        assert len(result) == 1
        assert result[0].source == SourceType.BLACKVUE

    def test_alias_gopro_videos(self):
        result = factory.parse_source_option("gopro_videos")
        assert len(result) == 1
        assert result[0].source == SourceType.GOPRO

    def test_alias_exiftool(self):
        result = factory.parse_source_option("exiftool")
        assert len(result) == 1
        assert result[0].source == SourceType.EXIFTOOL_RUNTIME

    def test_json_source(self):
        result = factory.parse_source_option('{"source": "gpx"}')
        assert len(result) == 1
        assert result[0].source == SourceType.GPX

    def test_comma_separated_sources(self):
        result = factory.parse_source_option("exif,gpx")
        assert len(result) == 2
        assert result[0].source == SourceType.EXIF
        assert result[1].source == SourceType.GPX

    def test_nmea_source(self):
        result = factory.parse_source_option("nmea")
        assert len(result) == 1
        assert result[0].source == SourceType.NMEA

    def test_camm_source(self):
        result = factory.parse_source_option("camm")
        assert len(result) == 1
        assert result[0].source == SourceType.CAMM


class TestIsReprocessable:
    def test_geotag_error_is_reprocessable(self):
        err = types.ErrorMetadata(
            filename=Path("/tmp/test.jpg"),
            filetype=types.FileType.IMAGE,
            error=exceptions.BankingPlatformGeoTaggingError("no gps"),
        )
        assert factory._is_reprocessable(err) is True

    def test_video_gps_not_found_is_reprocessable(self):
        err = types.ErrorMetadata(
            filename=Path("/tmp/test.mp4"),
            filetype=types.FileType.VIDEO,
            error=exceptions.BankingPlatformVideoGPSNotFoundError("no gps"),
        )
        assert factory._is_reprocessable(err) is True

    def test_generic_error_not_reprocessable(self):
        err = types.ErrorMetadata(
            filename=Path("/tmp/test.jpg"),
            filetype=types.FileType.IMAGE,
            error=RuntimeError("other"),
        )
        assert factory._is_reprocessable(err) is False

    def test_image_metadata_not_reprocessable(self):
        m = MagicMock(spec=types.ImageMetadata)
        assert factory._is_reprocessable(m) is False


class TestFilterImagesAndVideos:
    def test_no_filter(self, tmp_path):
        img = tmp_path / "test.jpg"
        img.touch()
        vid = tmp_path / "test.mp4"
        vid.touch()
        images, videos = factory._filter_images_and_videos([img, vid])
        assert img in images
        assert vid in videos

    def test_filter_images_only(self, tmp_path):
        img = tmp_path / "test.jpg"
        img.touch()
        vid = tmp_path / "test.mp4"
        vid.touch()
        images, videos = factory._filter_images_and_videos(
            [img, vid], filetypes={types.FileType.IMAGE}
        )
        assert img in images
        assert vid not in videos

    def test_filter_videos_only(self, tmp_path):
        img = tmp_path / "test.jpg"
        img.touch()
        vid = tmp_path / "test.mp4"
        vid.touch()
        images, videos = factory._filter_images_and_videos(
            [img, vid], filetypes={types.FileType.VIDEO}
        )
        assert img not in images
        assert vid in videos


class TestEnsureSourcePath:
    def test_raises_when_no_source_path(self):
        option = SourceOption(source=SourceType.GPX)
        with pytest.raises(exceptions.BankingPlatformBadParameterError):
            factory._ensure_source_path(option)

    def test_raises_when_source_path_is_none(self):
        option = SourceOption(
            source=SourceType.GPX,
            source_path=SourcePathOption(pattern="%f.gpx"),
        )
        with pytest.raises(exceptions.BankingPlatformBadParameterError):
            factory._ensure_source_path(option)

    def test_returns_source_path(self, tmp_path):
        gpx_file = tmp_path / "track.gpx"
        gpx_file.touch()
        option = SourceOption(
            source=SourceType.GPX,
            source_path=SourcePathOption(source_path=gpx_file),
        )
        result = factory._ensure_source_path(option)
        assert result == gpx_file


class TestBuildImageGeotag:
    def test_exif_source(self):
        option = SourceOption(source=SourceType.EXIF)
        result = factory._build_image_geotag(option)
        assert result is not None

    def test_native_source(self):
        option = SourceOption(source=SourceType.NATIVE)
        result = factory._build_image_geotag(option)
        assert result is not None

    def test_exiftool_runtime_source(self):
        option = SourceOption(source=SourceType.EXIFTOOL_RUNTIME)
        result = factory._build_image_geotag(option)
        assert result is not None

    def test_exiftool_xml_without_path_raises(self):
        option = SourceOption(source=SourceType.EXIFTOOL_XML)
        with pytest.raises(exceptions.BankingPlatformBadParameterError):
            factory._build_image_geotag(option)

    def test_gpx_source(self, tmp_path):
        gpx_file = tmp_path / "track.gpx"
        # Write minimal valid GPX
        gpx_file.write_text(
            '<?xml version="1.0"?><gpx><trk><trkseg><trkpt lat="0" lon="0"><time>2023-01-01T00:00:00Z</time></trkpt></trkseg></trk></gpx>'
        )
        option = SourceOption(
            source=SourceType.GPX,
            source_path=SourcePathOption(source_path=gpx_file),
        )
        result = factory._build_image_geotag(option)
        assert result is not None

    def test_nmea_source(self, tmp_path):
        nmea_file = tmp_path / "track.nmea"
        # Valid NMEA sentence with correct checksum
        nmea_file.write_text(
            "$GPRMC,120000,A,0000.0000,N,00000.0000,E,0,0,010123,0,E*6A\n"
        )
        option = SourceOption(
            source=SourceType.NMEA,
            source_path=SourcePathOption(source_path=nmea_file),
        )
        result = factory._build_image_geotag(option)
        assert result is not None

    def test_gopro_source(self, tmp_path):
        vid = tmp_path / "GH010001.mp4"
        vid.touch()
        option = SourceOption(
            source=SourceType.GOPRO,
            source_path=SourcePathOption(source_path=vid),
        )
        result = factory._build_image_geotag(option)
        assert result is not None


class TestProcess:
    def test_no_options_raises(self):
        with pytest.raises(ValueError, match="No geotag options"):
            factory.process([], [])

    @patch("banking_tools.compliance.factory._filter_images_and_videos")
    @patch("banking_tools.compliance.factory._build_image_geotag")
    def test_process_images(self, mock_build, mock_filter, tmp_path):
        img = tmp_path / "test.jpg"
        img.touch()

        mock_filter.return_value = ([img], [])
        mock_geotag = MagicMock()
        mock_metadata = MagicMock(spec=types.ImageMetadata)
        mock_metadata.filename = img
        mock_geotag.to_description.return_value = [mock_metadata]
        mock_build.return_value = mock_geotag

        options = [SourceOption(source=SourceType.EXIF)]
        result = factory.process([img], options)
        assert len(result) == 1
