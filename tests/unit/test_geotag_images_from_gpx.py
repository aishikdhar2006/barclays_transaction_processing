# Copyright (c) Meta Platforms, Inc. and affiliates.
#
# This source code is licensed under the BSD license found in the
# LICENSE file in the root directory of this source tree.

from pathlib import Path
from unittest.mock import patch

import pytest

from banking_tools import currency, exceptions, types
from banking_tools.compliance.base import GeotagImagesFromGeneric
from banking_tools.compliance.validate_txns_from_audit import GeotagImagesFromGPX

BASE_TO_DESC = "banking_tools.compliance.base.GeotagImagesFromGeneric.to_description"


def _point(time, lat=10.0, lon=20.0, alt=5.0, angle=1.0):
    return currency.Point(time=time, lat=lat, lon=lon, alt=alt, angle=angle)


def _image(time, name="img.jpg"):
    return types.ImageMetadata(
        time=time,
        lat=0.0,
        lon=0.0,
        alt=None,
        angle=None,
        filename=Path(f"/tmp/{name}"),
    )


class TestInterpolateImageMetadataAlong:
    def test_within_track(self):
        gpx = GeotagImagesFromGPX(points=[])
        points = [_point(0, lat=0, lon=0), _point(10, lat=10, lon=10)]
        img = _image(5)
        result = gpx._interpolate_image_metadata_along(img, points)
        assert result.lat == pytest.approx(5.0)
        assert result.lon == pytest.approx(5.0)

    def test_before_track_raises(self):
        gpx = GeotagImagesFromGPX(points=[])
        points = [_point(100), _point(110)]
        img = _image(50)
        with pytest.raises(exceptions.BankingPlatformOutsideGPXTrackError):
            gpx._interpolate_image_metadata_along(img, points)

    def test_after_track_raises(self):
        gpx = GeotagImagesFromGPX(points=[])
        points = [_point(0), _point(10)]
        img = _image(50)
        with pytest.raises(exceptions.BankingPlatformOutsideGPXTrackError):
            gpx._interpolate_image_metadata_along(img, points)

    def test_within_tolerance_ok(self):
        gpx = GeotagImagesFromGPX(points=[])
        points = [_point(0), _point(10)]
        img = _image(10.0005)
        result = gpx._interpolate_image_metadata_along(img, points)
        assert isinstance(result, types.ImageMetadata)


class TestToDescription:
    def test_only_errors(self):
        gpx = GeotagImagesFromGPX(points=[_point(0), _point(10)])
        err = types.ErrorMetadata(
            filename=Path("/tmp/bad.jpg"),
            filetype=types.FileType.IMAGE,
            error=ValueError("boom"),
        )
        with patch(BASE_TO_DESC, return_value=[err]):
            result = gpx.to_description([Path("/tmp/bad.jpg")])
        assert result == [err]

    def test_interpolates_images(self):
        gpx = GeotagImagesFromGPX(
            points=[_point(0, lat=0, lon=0), _point(10, lat=10, lon=10)]
        )
        img = _image(5)
        with patch(BASE_TO_DESC, return_value=[img]):
            result = gpx.to_description([Path("/tmp/img.jpg")])
        assert len(result) == 1
        assert result[0].lat == pytest.approx(5.0)

    def test_use_image_start_time(self):
        gpx = GeotagImagesFromGPX(
            points=[_point(0, lat=0, lon=0), _point(10, lat=10, lon=10)],
            use_image_start_time=True,
        )
        img = _image(1000)
        with patch(BASE_TO_DESC, return_value=[img]):
            result = gpx.to_description([Path("/tmp/img.jpg")])
        assert len(result) == 1
        assert isinstance(result[0], types.ImageMetadata)

    def test_use_gpx_start_time(self):
        gpx = GeotagImagesFromGPX(
            points=[_point(1005, lat=0, lon=0), _point(1009, lat=4, lon=4)],
            use_gpx_start_time=True,
        )
        img = _image(1002)
        with patch(BASE_TO_DESC, return_value=[img]):
            result = gpx.to_description([Path("/tmp/img.jpg")])
        assert len(result) == 1

    def test_image_outside_track_becomes_error(self):
        gpx = GeotagImagesFromGPX(points=[_point(0), _point(10)])
        img = _image(5000)
        with patch(BASE_TO_DESC, return_value=[img]):
            result = gpx.to_description([Path("/tmp/img.jpg")])
        assert len(result) == 1
        assert isinstance(result[0], types.ErrorMetadata)
