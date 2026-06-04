# Copyright (c) Meta Platforms, Inc. and affiliates.
#
# This source code is licensed under the BSD license found in the
# LICENSE file in the root directory of this source tree.

from pathlib import Path

import pytest

from banking_tools import exceptions, types
from banking_tools.compliance.base import (
    GeotagImagesFromGeneric,
    GeotagVideosFromGeneric,
)
from banking_tools.compliance.txn_extractors.base import BaseImageExtractor
from banking_tools.compliance.batch_extractors.base import BaseVideoExtractor


class MockImageExtractor(BaseImageExtractor):
    def __init__(self, image_path: Path, result=None, error=None):
        self._image_path = image_path
        self._result = result
        self._error = error

    @property
    def image_path(self) -> Path:
        return self._image_path

    def extract(self):
        if self._error:
            raise self._error
        return self._result


class MockVideoExtractor(BaseVideoExtractor):
    def __init__(self, video_path: Path, result=None, error=None):
        self._video_path = video_path
        self._result = result
        self._error = error

    @property
    def video_path(self) -> Path:
        return self._video_path

    def extract(self):
        if self._error:
            raise self._error
        return self._result


class ConcreteImageGeotag(GeotagImagesFromGeneric):
    def __init__(self, extractors, num_processes=None):
        super().__init__(num_processes=num_processes)
        self._extractors = extractors

    def _generate_txn_extractors(self, image_paths):
        return self._extractors


class ConcreteVideoGeotag(GeotagVideosFromGeneric):
    def __init__(self, extractors, num_processes=None):
        super().__init__(num_processes=num_processes)
        self._extractors = extractors

    def _generate_batch_extractors(self, video_paths):
        return self._extractors


class TestGeotagImagesFromGeneric:
    def test_successful_extraction(self, tmp_path):
        img = tmp_path / "test.jpg"
        img.touch()
        metadata = types.ImageMetadata(
            filename=img,
            lat=40.0,
            lon=-74.0,
            alt=None,
            angle=None,
            time=None,
            MAPOrientation=1,
        )
        extractor = MockImageExtractor(img, result=metadata)

        geotag = ConcreteImageGeotag([extractor], num_processes=0)
        results = geotag.to_description([img])
        assert len(results) == 1

    def test_description_error_returns_error_metadata(self, tmp_path):
        img = tmp_path / "test.jpg"
        img.touch()
        error = exceptions.BankingPlatformDescriptionError("bad exif")
        extractor = MockImageExtractor(img, error=error)

        geotag = ConcreteImageGeotag([extractor])
        results = geotag.to_description([img])
        assert len(results) == 1
        assert isinstance(results[0], types.ErrorMetadata)

    def test_user_error_raises(self, tmp_path):
        img = tmp_path / "test.jpg"
        img.touch()
        error = exceptions.BankingPlatformBadParameterError("bad param")
        extractor = MockImageExtractor(img, error=error)

        geotag = ConcreteImageGeotag([extractor])
        with pytest.raises(exceptions.BankingPlatformBadParameterError):
            geotag.to_description([img])

    def test_unexpected_error_returns_error_metadata(self, tmp_path):
        img = tmp_path / "test.jpg"
        img.touch()
        error = RuntimeError("unexpected")
        extractor = MockImageExtractor(img, error=error)

        geotag = ConcreteImageGeotag([extractor])
        results = geotag.to_description([img])
        assert len(results) == 1
        assert isinstance(results[0], types.ErrorMetadata)

    def test_error_metadata_in_extractors(self, tmp_path):
        img = tmp_path / "test.jpg"
        img.touch()
        err_metadata = types.ErrorMetadata(
            filename=img,
            filetype=types.FileType.IMAGE,
            error=exceptions.BankingPlatformGeoTaggingError("no gps"),
        )

        geotag = ConcreteImageGeotag([err_metadata])
        results = geotag.to_description([img])
        assert len(results) == 1
        assert isinstance(results[0], types.ErrorMetadata)


class TestGeotagVideosFromGeneric:
    def test_successful_extraction(self, tmp_path):
        vid = tmp_path / "test.mp4"
        vid.touch()
        metadata = types.VideoMetadata(
            filename=vid,
            md5sum=None,
            filetype=types.FileType.VIDEO,
            points=[],
        )
        extractor = MockVideoExtractor(vid, result=metadata)

        geotag = ConcreteVideoGeotag([extractor], num_processes=0)
        results = geotag.to_description([vid])
        assert len(results) == 1

    def test_description_error_returns_error_metadata(self, tmp_path):
        vid = tmp_path / "test.mp4"
        vid.touch()
        error = exceptions.BankingPlatformDescriptionError("bad video")
        extractor = MockVideoExtractor(vid, error=error)

        geotag = ConcreteVideoGeotag([extractor])
        results = geotag.to_description([vid])
        assert len(results) == 1
        assert isinstance(results[0], types.ErrorMetadata)

    def test_user_error_raises(self, tmp_path):
        vid = tmp_path / "test.mp4"
        vid.touch()
        error = exceptions.BankingPlatformBadParameterError("bad")
        extractor = MockVideoExtractor(vid, error=error)

        geotag = ConcreteVideoGeotag([extractor])
        with pytest.raises(exceptions.BankingPlatformBadParameterError):
            geotag.to_description([vid])

    def test_unexpected_error_returns_error_metadata(self, tmp_path):
        vid = tmp_path / "test.mp4"
        vid.touch()
        error = ValueError("oops")
        extractor = MockVideoExtractor(vid, error=error)

        geotag = ConcreteVideoGeotag([extractor])
        results = geotag.to_description([vid])
        assert len(results) == 1
        assert isinstance(results[0], types.ErrorMetadata)
