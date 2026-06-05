# Copyright (c) Meta Platforms, Inc. and affiliates.
#
# This source code is licensed under the BSD license found in the
# LICENSE file in the root directory of this source tree.

import typing as T
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from banking_tools import exceptions, types
from banking_tools.compliance import base
from banking_tools.compliance.base import (
    GeotagImagesFromGeneric,
    GeotagVideosFromGeneric,
)


def _image_md(path="/tmp/a.jpg"):
    return types.ImageMetadata(
        time=0.0, lat=1.0, lon=2.0, alt=None, angle=None, filename=Path(path)
    )


def _video_md(path="/tmp/v.mp4"):
    return types.VideoMetadata(
        filename=Path(path), filetype=types.FileType.VIDEO, points=[]
    )


class TestImageRunExtraction:
    def test_success(self):
        extractor = MagicMock(image_path=Path("/tmp/a.jpg"))
        extractor.extract.return_value = _image_md()
        result = GeotagImagesFromGeneric.run_extraction(extractor)
        assert isinstance(result, types.ImageMetadata)

    def test_description_error_becomes_error_metadata(self):
        extractor = MagicMock(image_path=Path("/tmp/a.jpg"))
        extractor.extract.side_effect = exceptions.BankingPlatformGPXEmptyError("empty")
        result = GeotagImagesFromGeneric.run_extraction(extractor)
        assert isinstance(result, types.ErrorMetadata)

    def test_user_error_reraised(self):
        extractor = MagicMock(image_path=Path("/tmp/a.jpg"))
        extractor.extract.side_effect = exceptions.BankingPlatformBadParameterError(
            "bad"
        )
        with pytest.raises(exceptions.BankingPlatformBadParameterError):
            GeotagImagesFromGeneric.run_extraction(extractor)

    def test_generic_error_becomes_error_metadata(self):
        extractor = MagicMock(image_path=Path("/tmp/a.jpg"))
        extractor.extract.side_effect = RuntimeError("boom")
        result = GeotagImagesFromGeneric.run_extraction(extractor)
        assert isinstance(result, types.ErrorMetadata)


class TestVideoRunExtraction:
    def test_success(self):
        extractor = MagicMock(video_path=Path("/tmp/v.mp4"))
        extractor.extract.return_value = _video_md()
        result = GeotagVideosFromGeneric.run_extraction(extractor)
        assert isinstance(result, types.VideoMetadata)

    def test_description_error_becomes_error_metadata(self):
        extractor = MagicMock(video_path=Path("/tmp/v.mp4"))
        extractor.extract.side_effect = exceptions.BankingPlatformVideoGPSNotFoundError(
            "no gps"
        )
        result = GeotagVideosFromGeneric.run_extraction(extractor)
        assert isinstance(result, types.ErrorMetadata)

    def test_generic_error_becomes_error_metadata(self):
        extractor = MagicMock(video_path=Path("/tmp/v.mp4"))
        extractor.extract.side_effect = RuntimeError("boom")
        result = GeotagVideosFromGeneric.run_extraction(extractor)
        assert isinstance(result, types.ErrorMetadata)


class _ConcreteImages(GeotagImagesFromGeneric):
    def __init__(self, extractor_or_errors, **kwargs):
        super().__init__(**kwargs)
        self._items = extractor_or_errors

    def _generate_txn_extractors(self, image_paths):
        return self._items


class TestToDescription:
    @patch.object(base.utils, "mp_map_maybe")
    def test_combines_results_and_errors(self, mock_map):
        extractor = MagicMock(image_path=Path("/tmp/a.jpg"))
        err = types.ErrorMetadata(
            filename=Path("/tmp/b.jpg"),
            filetype=types.FileType.IMAGE,
            error=ValueError("x"),
        )
        mock_map.return_value = [_image_md("/tmp/a.jpg")]
        obj = _ConcreteImages([extractor, err])
        result = obj.to_description([Path("/tmp/a.jpg"), Path("/tmp/b.jpg")])
        assert len(result) == 2
        kinds = sorted(type(m).__name__ for m in result)
        assert kinds == ["ErrorMetadata", "ImageMetadata"]
