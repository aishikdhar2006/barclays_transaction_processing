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
    InterpolationOption,
    SourceOption,
    SourcePathOption,
    SourceType,
    validate_option,
)


class TestParseSourceOption:
    def test_native(self):
        result = factory.parse_source_option("native")
        assert len(result) == 1
        assert result[0].source == SourceType.NATIVE

    def test_exif(self):
        result = factory.parse_source_option("exif")
        assert result[0].source == SourceType.EXIF

    def test_gpx(self):
        result = factory.parse_source_option("gpx")
        assert result[0].source == SourceType.GPX

    def test_nmea(self):
        result = factory.parse_source_option("nmea")
        assert result[0].source == SourceType.NMEA

    def test_alias_blackvue_videos(self):
        result = factory.parse_source_option("blackvue_videos")
        assert result[0].source == SourceType.BLACKVUE

    def test_alias_gopro_videos(self):
        result = factory.parse_source_option("gopro_videos")
        assert result[0].source == SourceType.GOPRO

    def test_alias_exiftool(self):
        result = factory.parse_source_option("exiftool")
        assert result[0].source == SourceType.EXIFTOOL_RUNTIME

    def test_comma_separated(self):
        result = factory.parse_source_option("exif,gpx")
        assert len(result) == 2
        assert result[0].source == SourceType.EXIF
        assert result[1].source == SourceType.GPX

    def test_json_source(self):
        result = factory.parse_source_option('{"source": "gpx"}')
        assert result[0].source == SourceType.GPX


class TestFilterImagesAndVideos:
    def test_all_filetypes(self, tmpdir):
        img = Path(str(tmpdir.join("test.jpg")))
        img.write_text("x")
        vid = Path(str(tmpdir.join("test.mp4")))
        vid.write_text("x")
        images, videos = factory._filter_images_and_videos([img, vid])
        assert len(images) == 1
        assert len(videos) == 1

    def test_images_only(self, tmpdir):
        img = Path(str(tmpdir.join("test.jpg")))
        img.write_text("x")
        vid = Path(str(tmpdir.join("test.mp4")))
        vid.write_text("x")
        images, videos = factory._filter_images_and_videos(
            [img, vid], filetypes={types.FileType.IMAGE}
        )
        assert len(images) == 1
        assert len(videos) == 0

    def test_videos_only(self, tmpdir):
        img = Path(str(tmpdir.join("test.jpg")))
        img.write_text("x")
        vid = Path(str(tmpdir.join("test.mp4")))
        vid.write_text("x")
        images, videos = factory._filter_images_and_videos(
            [img, vid], filetypes={types.FileType.VIDEO}
        )
        assert len(images) == 0
        assert len(videos) == 1


class TestIsReprocessable:
    def test_geotagging_error(self):
        err = types.ErrorMetadata(
            filename=Path("test.jpg"),
            filetype=types.FileType.IMAGE,
            error=exceptions.BankingPlatformGeoTaggingError("err"),
        )
        assert factory._is_reprocessable(err) is True

    def test_video_gps_not_found(self):
        err = types.ErrorMetadata(
            filename=Path("test.mp4"),
            filetype=types.FileType.VIDEO,
            error=exceptions.BankingPlatformVideoGPSNotFoundError("err"),
        )
        assert factory._is_reprocessable(err) is True

    def test_non_reprocessable_error(self):
        err = types.ErrorMetadata(
            filename=Path("test.jpg"),
            filetype=types.FileType.IMAGE,
            error=RuntimeError("err"),
        )
        assert factory._is_reprocessable(err) is False

    def test_valid_metadata_not_reprocessable(self):
        m = types.ImageMetadata(
            time=0.0, lat=0.0, lon=0.0, alt=None, angle=None, filename=Path("t.jpg")
        )
        assert factory._is_reprocessable(m) is False


class TestEnsureSourcePath:
    def test_with_source_path(self):
        opt = SourceOption(
            SourceType.GPX,
            source_path=SourcePathOption(source_path=Path("/tmp/test.gpx")),
        )
        result = factory._ensure_source_path(opt)
        assert result == Path("/tmp/test.gpx")

    def test_without_source_path_raises(self):
        opt = SourceOption(SourceType.GPX)
        with pytest.raises(exceptions.BankingPlatformBadParameterError):
            factory._ensure_source_path(opt)


class TestBuildImageGeotag:
    def test_native(self):
        opt = SourceOption(SourceType.NATIVE)
        result = factory._build_image_geotag(opt)
        assert result is not None
        assert "EXIF" in result.__class__.__name__

    def test_exif(self):
        opt = SourceOption(SourceType.EXIF)
        result = factory._build_image_geotag(opt)
        assert result is not None

    def test_exiftool_runtime(self):
        opt = SourceOption(SourceType.EXIFTOOL_RUNTIME)
        result = factory._build_image_geotag(opt)
        assert result is not None

    def test_exiftool_xml_without_source_path_raises(self):
        opt = SourceOption(SourceType.EXIFTOOL_XML)
        with pytest.raises(exceptions.BankingPlatformBadParameterError):
            factory._build_image_geotag(opt)

    def test_exiftool_xml_with_source_path(self):
        opt = SourceOption(
            SourceType.EXIFTOOL_XML,
            source_path=SourcePathOption(source_path=Path("/tmp/test.xml")),
        )
        result = factory._build_image_geotag(opt)
        assert result is not None

    @patch(
        "banking_tools.compliance.validate_txns_from_audit_file.GeotagImagesFromGPXFile"
    )
    def test_gpx(self, mock_gpx):
        opt = SourceOption(
            SourceType.GPX,
            source_path=SourcePathOption(source_path=Path("/tmp/test.gpx")),
        )
        result = factory._build_image_geotag(opt)
        assert result is not None
        mock_gpx.assert_called_once()

    @patch(
        "banking_tools.compliance.validate_txns_from_feed_file.GeotagImagesFromNMEAFile"
    )
    def test_nmea(self, mock_nmea):
        opt = SourceOption(
            SourceType.NMEA,
            source_path=SourcePathOption(source_path=Path("/tmp/test.nmea")),
        )
        result = factory._build_image_geotag(opt)
        assert result is not None
        mock_nmea.assert_called_once()

    @patch(
        "banking_tools.compliance.validate_txns_from_batch.GeotagImageSamplesFromVideo"
    )
    def test_gopro(self, mock_gopro):
        opt = SourceOption(
            SourceType.GOPRO,
            source_path=SourcePathOption(source_path=Path("/tmp/test.mp4")),
        )
        result = factory._build_image_geotag(opt)
        assert result is not None
        mock_gopro.assert_called_once()

    @patch(
        "banking_tools.compliance.validate_txns_from_audit_file.GeotagImagesFromGPXFile"
    )
    def test_with_custom_interpolation(self, mock_gpx):
        opt = SourceOption(
            SourceType.GPX,
            source_path=SourcePathOption(source_path=Path("/tmp/test.gpx")),
            interpolation=InterpolationOption(offset_time=5.0, use_gpx_start_time=True),
        )
        result = factory._build_image_geotag(opt)
        assert result is not None


class TestBuildVideoGeotag:
    def test_native(self):
        opt = SourceOption(SourceType.NATIVE)
        result = factory._build_video_geotag(opt)
        assert result is not None

    def test_exiftool_runtime(self):
        opt = SourceOption(SourceType.EXIFTOOL_RUNTIME)
        result = factory._build_video_geotag(opt)
        assert result is not None

    def test_exiftool_xml_with_source_path(self):
        opt = SourceOption(
            SourceType.EXIFTOOL_XML,
            source_path=SourcePathOption(source_path=Path("/tmp/test.xml")),
        )
        result = factory._build_video_geotag(opt)
        assert result is not None

    def test_exiftool_xml_without_source_path_raises(self):
        opt = SourceOption(SourceType.EXIFTOOL_XML)
        with pytest.raises(exceptions.BankingPlatformBadParameterError):
            factory._build_video_geotag(opt)

    @patch("banking_tools.compliance.validate_batches_from_audit.GeotagVideosFromGPX")
    def test_gpx(self, mock_gpx):
        opt = SourceOption(
            SourceType.GPX,
            source_path=SourcePathOption(source_path=Path("/tmp/test.gpx")),
        )
        result = factory._build_video_geotag(opt)
        assert result is not None

    def test_nmea_returns_none(self):
        opt = SourceOption(
            SourceType.NMEA,
            source_path=SourcePathOption(source_path=Path("/tmp/test.nmea")),
        )
        result = factory._build_video_geotag(opt)
        assert result is None

    def test_exif_returns_none(self):
        opt = SourceOption(SourceType.EXIF)
        assert factory._build_video_geotag(opt) is None

    def test_gopro_returns_none(self):
        opt = SourceOption(SourceType.GOPRO)
        assert factory._build_video_geotag(opt) is None


class TestProcess:
    def test_no_options_raises(self):
        with pytest.raises(ValueError, match="No geotag options"):
            factory.process([], [])

    @patch("banking_tools.compliance.factory._build_image_geotag")
    @patch("banking_tools.compliance.factory._filter_images_and_videos")
    def test_with_empty_paths(self, mock_filter, mock_build):
        mock_filter.return_value = ([], [])
        opts = [SourceOption(SourceType.NATIVE)]
        result = factory.process([], opts)
        assert result == []


class TestSourceOption:
    def test_from_dict_basic(self):
        opt = SourceOption.from_dict({"source": "native"})
        assert opt.source == SourceType.NATIVE

    def test_from_dict_with_filetypes(self):
        opt = SourceOption.from_dict({"source": "native", "filetypes": ["image"]})
        assert types.FileType.IMAGE in opt.filetypes

    def test_from_dict_with_interpolation(self):
        opt = SourceOption.from_dict(
            {
                "source": "gpx",
                "interpolation_offset_time": 5.0,
                "interpolation_use_gpx_start_time": True,
            }
        )
        assert opt.interpolation.offset_time == 5.0
        assert opt.interpolation.use_gpx_start_time is True


class TestSourcePathOption:
    def test_pattern_resolve(self):
        opt = SourcePathOption(pattern="videos/%g_sub%e")
        result = opt.resolve(Path("/data/video1.mp4"))
        assert "video1_sub.mp4" in str(result)

    def test_source_path_resolve(self):
        opt = SourcePathOption(source_path=Path("/foo/bar.mp4"))
        result = opt.resolve(Path("/baz/qux.mp4"))
        assert result == Path("/foo/bar.mp4")

    def test_neither_raises(self):
        with pytest.raises(ValueError, match="Either pattern or source_path"):
            SourcePathOption()


class TestInterpolationOption:
    def test_defaults(self):
        opt = InterpolationOption()
        assert opt.offset_time == 0.0
        assert opt.use_gpx_start_time is False


class TestValidateOption:
    def test_valid(self):
        validate_option({"source": "native"})

    def test_invalid_source(self):
        import jsonschema

        with pytest.raises(jsonschema.ValidationError):
            validate_option({"source": "invalid_source_type_xyz"})
