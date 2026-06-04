# Copyright (c) Meta Platforms, Inc. and affiliates.
#
# This source code is licensed under the BSD license found in the
# LICENSE file in the root directory of this source tree.

from pathlib import Path
from unittest.mock import patch

import pytest

from banking_tools import currency, exceptions, types
from banking_tools.compliance import validate_txns_from_audit
from banking_tools.compliance.validate_txns_from_audit import GeotagImagesFromGPX


def _pt(time, lat=10.0, lon=20.0, alt=5.0, angle=90.0):
    return currency.Point(time=time, lat=lat, lon=lon, alt=alt, angle=angle)


def _img(time, name="img.jpg", tmp_path=None):
    path = (tmp_path / name) if tmp_path else Path(name)
    return types.ImageMetadata(
        filename=path,
        lat=0.0,
        lon=0.0,
        alt=None,
        angle=None,
        time=time,
        MAPOrientation=1,
    )


class TestInterpolateImageMetadataAlong:
    def test_within_range(self):
        geotag = GeotagImagesFromGPX([], num_processes=0)
        points = [_pt(0.0), _pt(10.0)]
        img = _img(5.0)
        result = geotag._interpolate_image_metadata_along(img, points)
        assert result.lat == pytest.approx(10.0)

    def test_before_start_within_tolerance(self):
        geotag = GeotagImagesFromGPX([], num_processes=0)
        points = [_pt(10.0), _pt(20.0)]
        img = _img(10.0 - 0.0005)
        result = geotag._interpolate_image_metadata_along(img, points)
        assert result is not None

    def test_before_start_raises(self):
        geotag = GeotagImagesFromGPX([], num_processes=0)
        points = [_pt(10.0), _pt(20.0)]
        img = _img(5.0)
        with pytest.raises(exceptions.BankingPlatformOutsideGPXTrackError):
            geotag._interpolate_image_metadata_along(img, points)

    def test_after_end_raises(self):
        geotag = GeotagImagesFromGPX([], num_processes=0)
        points = [_pt(0.0), _pt(10.0)]
        img = _img(20.0)
        with pytest.raises(exceptions.BankingPlatformOutsideGPXTrackError):
            geotag._interpolate_image_metadata_along(img, points)


class TestGenerateImageExtractors:
    def test_returns_exif_extractors(self, tmp_path):
        geotag = GeotagImagesFromGPX([_pt(0.0)], num_processes=0)
        paths = [tmp_path / "a.jpg", tmp_path / "b.jpg"]
        extractors = geotag._generate_txn_extractors(paths)
        assert len(extractors) == 2


class TestToDescription:
    def test_only_errors_returns_early(self, tmp_path):
        err = types.describe_error_metadata(
            exceptions.BankingPlatformDescriptionError("bad"),
            tmp_path / "a.jpg",
            filetype=types.FileType.IMAGE,
        )
        geotag = GeotagImagesFromGPX([_pt(0.0), _pt(10.0)], num_processes=0)
        with patch.object(
            validate_txns_from_audit.GeotagImagesFromGeneric,
            "to_description",
            return_value=[err],
        ):
            result = geotag.to_description([tmp_path / "a.jpg"])
        assert result == [err]

    def test_interpolates_with_image_start_time(self, tmp_path):
        img = _img(1000.0, tmp_path=tmp_path)
        geotag = GeotagImagesFromGPX(
            [_pt(0.0), _pt(10.0)], use_image_start_time=True, num_processes=0
        )
        with patch.object(
            validate_txns_from_audit.GeotagImagesFromGeneric,
            "to_description",
            return_value=[img],
        ):
            result = geotag.to_description([tmp_path / "img.jpg"])
        assert len(result) == 1
        assert isinstance(result[0], types.ImageMetadata)

    def test_use_gpx_start_time_offset(self, tmp_path):
        img = _img(2.0, tmp_path=tmp_path)
        geotag = GeotagImagesFromGPX(
            [_pt(1005.0), _pt(1009.0)], use_gpx_start_time=True, num_processes=0
        )
        with patch.object(
            validate_txns_from_audit.GeotagImagesFromGeneric,
            "to_description",
            return_value=[img],
        ):
            result = geotag.to_description([tmp_path / "img.jpg"])
        assert len(result) == 1

    def test_outside_track_becomes_error(self, tmp_path):
        img = _img(9999.0, tmp_path=tmp_path)
        geotag = GeotagImagesFromGPX([_pt(0.0), _pt(10.0)], num_processes=0)
        with patch.object(
            validate_txns_from_audit.GeotagImagesFromGeneric,
            "to_description",
            return_value=[img],
        ):
            result = geotag.to_description([tmp_path / "img.jpg"])
        assert isinstance(result[0], types.ErrorMetadata)
