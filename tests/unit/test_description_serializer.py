# Copyright (c) Meta Platforms, Inc. and affiliates.
#
# This source code is licensed under the BSD license found in the
# LICENSE file in the root directory of this source tree.

import datetime
from pathlib import Path

import pytest

from banking_tools import exceptions, types
from banking_tools.serializer.description import (
    build_capture_time,
    desc_file_to_exif,
    validate_and_fail_metadata,
    validate_image_desc,
    validate_video_desc,
)


class TestDescFileToExif:
    def test_keeps_map_keys_removes_not_needed(self):
        desc = {
            "MAPLatitude": 40.7128,
            "MAPLongitude": -74.006,
            "MAPSequenceUUID": "uuid-123",
            "MAPCaptureTime": "2023-06-15T12:00:00Z",
            "MAPCompassHeading": {"TrueHeading": 180},
            "other_key": "value",
        }
        result = desc_file_to_exif(desc)
        # MAPSequenceUUID is in `not_needed` so it's excluded
        assert "MAPSequenceUUID" not in result
        # MAP prefixed keys are kept
        assert "MAPLatitude" in result
        assert "MAPCaptureTime" in result
        assert "MAPCompassHeading" in result
        # Non-MAP keys are excluded
        assert "other_key" not in result

    def test_empty_desc(self):
        result = desc_file_to_exif({})
        assert result == {}


class TestValidateImageDesc:
    def test_valid_desc(self):
        desc = {
            "MAPLatitude": 40.7128,
            "MAPLongitude": -74.006,
            "MAPCaptureTime": "2023_06_15_12_00_00_000",
            "filename": "/test.jpg",
            "filetype": "image",
        }
        validate_image_desc(desc)

    def test_invalid_desc_raises(self):
        desc = {"MAPLatitude": "not a number"}
        with pytest.raises(exceptions.BankingPlatformMetadataValidationError):
            validate_image_desc(desc)


class TestValidateVideoDesc:
    def test_valid_desc(self):
        desc = {
            "filename": "/test.mp4",
            "filetype": "video",
            "MAPGPSTrack": [[0, -74.006, 40.7128, None, None, None, None]],
        }
        validate_video_desc(desc)

    def test_invalid_desc_raises(self):
        desc = {"MAPLatitude": "not a number"}
        with pytest.raises(exceptions.BankingPlatformMetadataValidationError):
            validate_video_desc(desc)


class TestValidateAndFailMetadata:
    def test_error_metadata_passthrough(self):
        error = types.ErrorMetadata(
            filename=Path("/test.jpg"),
            filetype=types.FileType.IMAGE,
            error=Exception("test"),
        )
        result = validate_and_fail_metadata(error)
        assert result is error

    def test_valid_image_metadata(self, tmp_path):
        img = tmp_path / "test.jpg"
        img.touch()
        metadata = types.ImageMetadata(
            filename=img,
            lat=40.7128,
            lon=-74.006,
            time=datetime.datetime(2023, 6, 15, 12, 0, 0, tzinfo=datetime.timezone.utc),
            angle=None,
            alt=None,
        )
        result = validate_and_fail_metadata(metadata)
        assert isinstance(result, types.ImageMetadata)

    def test_file_not_found(self, tmp_path):
        metadata = types.ImageMetadata(
            filename=tmp_path / "nonexistent.jpg",
            lat=40.7128,
            lon=-74.006,
            time=datetime.datetime(2023, 6, 15, 12, 0, 0, tzinfo=datetime.timezone.utc),
            angle=None,
            alt=None,
        )
        result = validate_and_fail_metadata(metadata)
        assert isinstance(result, types.ErrorMetadata)


class TestBuildCaptureTime:
    def test_format(self):
        dt = datetime.datetime(
            2023, 6, 15, 12, 30, 45, 123000, tzinfo=datetime.timezone.utc
        )
        result = build_capture_time(dt)
        assert "2023_06_15_12_30_45_123" in result
