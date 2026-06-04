# Copyright (c) Meta Platforms, Inc. and affiliates.
#
# This source code is licensed under the BSD license found in the
# LICENSE file in the root directory of this source tree.

from pathlib import Path

import pytest

from banking_tools import types
from banking_tools.compliance.options import (
    InterpolationOption,
    SourceOption,
    SourcePathOption,
    SourceType,
    validate_option,
)


class TestSourceType:
    def test_native(self):
        assert SourceType("native") == SourceType.NATIVE

    def test_gpx(self):
        assert SourceType("gpx") == SourceType.GPX

    def test_nmea(self):
        assert SourceType("nmea") == SourceType.NMEA

    def test_invalid_raises(self):
        with pytest.raises(ValueError):
            SourceType("invalid_source")


class TestSourcePathOption:
    def test_source_path(self):
        opt = SourcePathOption(source_path=Path("/foo/bar.gpx"))
        assert opt.resolve(Path("/baz/qux.mp4")) == Path("/foo/bar.gpx")

    def test_pattern_with_f(self):
        opt = SourcePathOption(pattern="%f.gpx")
        result = opt.resolve(Path("/data/video1.mp4"))
        assert result.name == "video1.mp4.gpx"

    def test_pattern_with_g_and_e(self):
        opt = SourcePathOption(pattern="tracks/%g%e")
        result = opt.resolve(Path("/data/video1.mp4"))
        assert "tracks" in str(result)
        assert "video1.mp4" in str(result)

    def test_absolute_pattern(self):
        opt = SourcePathOption(pattern="/abs/path/%f")
        result = opt.resolve(Path("/tmp/abc.mov"))
        assert result == Path("/abs/path/abc.mov")

    def test_neither_raises(self):
        with pytest.raises(ValueError, match="Either pattern or source_path"):
            SourcePathOption()


class TestInterpolationOption:
    def test_defaults(self):
        opt = InterpolationOption()
        assert opt.offset_time == 0.0
        assert opt.use_gpx_start_time is False

    def test_custom_values(self):
        opt = InterpolationOption(offset_time=5.0, use_gpx_start_time=True)
        assert opt.offset_time == 5.0
        assert opt.use_gpx_start_time is True


class TestSourceOption:
    def test_basic_creation(self):
        opt = SourceOption(source=SourceType.NATIVE)
        assert opt.source == SourceType.NATIVE
        assert opt.filetypes is None
        assert opt.num_processes is None
        assert opt.source_path is None
        assert opt.interpolation is None

    def test_from_dict_basic(self):
        opt = SourceOption.from_dict({"source": "gpx"})
        assert opt.source == SourceType.GPX

    def test_from_dict_with_filetypes(self):
        opt = SourceOption.from_dict({"source": "native", "filetypes": ["image"]})
        assert types.FileType.IMAGE in opt.filetypes

    def test_from_dict_with_source_path(self):
        opt = SourceOption.from_dict({"source": "gpx", "source_path": "/tmp/track.gpx"})
        assert opt.source_path is not None
        assert opt.source_path.source_path == Path("/tmp/track.gpx")

    def test_from_dict_with_pattern(self):
        opt = SourceOption.from_dict({"source": "gpx", "pattern": "%g.gpx"})
        assert opt.source_path is not None
        assert opt.source_path.pattern == "%g.gpx"

    def test_from_dict_with_interpolation(self):
        opt = SourceOption.from_dict(
            {
                "source": "gpx",
                "interpolation_offset_time": 2.5,
                "interpolation_use_gpx_start_time": True,
            }
        )
        assert opt.interpolation is not None
        assert opt.interpolation.offset_time == 2.5
        assert opt.interpolation.use_gpx_start_time is True

    def test_from_dict_with_alias(self):
        opt = SourceOption.from_dict({"source": "gopro_videos"})
        assert opt.source == SourceType.GOPRO

    def test_from_dict_ignores_none_values(self):
        # The schema does not allow None for filetypes, so only test source_path
        opt = SourceOption.from_dict({"source": "native"})
        assert opt.filetypes is None
        assert opt.source_path is None


class TestValidateOption:
    def test_valid_option(self):
        # Should not raise
        validate_option({"source": "native"})

    def test_missing_source_raises(self):
        import jsonschema

        with pytest.raises(jsonschema.ValidationError):
            validate_option({})

    def test_invalid_source_raises(self):
        import jsonschema

        with pytest.raises(jsonschema.ValidationError):
            validate_option({"source": "invalid_abc"})
