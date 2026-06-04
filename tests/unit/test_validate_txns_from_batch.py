# Copyright (c) Meta Platforms, Inc. and affiliates.
#
# This source code is licensed under the BSD license found in the
# LICENSE file in the root directory of this source tree.

from unittest.mock import MagicMock, patch

from banking_tools import currency, exceptions, types
from banking_tools.compliance import validate_txns_from_batch
from banking_tools.compliance.validate_txns_from_batch import (
    GeotagImageSamplesFromVideo,
    GeotagImagesFromVideo,
)


def _video_metadata(tmp_path, name="vid.mp4"):
    return types.VideoMetadata(
        filename=tmp_path / name,
        filesize=10,
        filetype=types.FileType.GOPRO,
        points=[currency.Point(time=0.0, lat=1.0, lon=2.0, alt=None, angle=None)],
        make="GoPro",
        model="Hero",
    )


def _image_metadata(path):
    return types.ImageMetadata(
        filename=path,
        lat=1.0,
        lon=2.0,
        alt=None,
        angle=None,
        time=0.0,
        MAPOrientation=1,
    )


class TestGeotagImagesFromVideo:
    def test_video_error_propagates_to_samples(self, tmp_path):
        err_md = types.describe_error_metadata(
            exceptions.BankingPlatformVideoGPSNotFoundError("no gps"),
            tmp_path / "vid.mp4",
            filetype=types.FileType.VIDEO,
        )
        sample = tmp_path / "vid_000.jpg"
        geotag = GeotagImagesFromVideo([err_md], num_processes=0)
        with patch.object(
            validate_txns_from_batch.utils,
            "filter_video_samples",
            return_value=[sample],
        ):
            result = geotag.to_description([sample])
        assert len(result) == 1
        assert isinstance(result[0], types.ErrorMetadata)

    def test_successful_geotag_sets_device_fields(self, tmp_path):
        vm = _video_metadata(tmp_path)
        sample = tmp_path / "vid_000.jpg"
        img_md = _image_metadata(sample)
        mock_geotag = MagicMock()
        mock_geotag.to_description.return_value = [img_md]
        geotag = GeotagImagesFromVideo([vm], num_processes=0)
        with (
            patch.object(
                validate_txns_from_batch.utils,
                "filter_video_samples",
                return_value=[sample],
            ),
            patch.object(
                validate_txns_from_batch,
                "GeotagImagesFromGPX",
                return_value=mock_geotag,
            ),
        ):
            result = geotag.to_description([sample])
        assert result[0].MAPDeviceMake == "GoPro"
        assert result[0].MAPDeviceModel == "Hero"


class TestGeotagImageSamplesFromVideo:
    def test_orchestration(self, tmp_path):
        source = tmp_path / "source"
        source.mkdir()
        video_path = source / "vid.mp4"
        sample = tmp_path / "vid_000.jpg"
        vm = _video_metadata(source)
        with (
            patch.object(
                validate_txns_from_batch.utils, "find_videos", return_value=[video_path]
            ),
            patch.object(
                validate_txns_from_batch.utils,
                "find_all_image_samples",
                return_value={video_path: [sample]},
            ),
            patch.object(
                validate_txns_from_batch.GeotagVideosFromVideo,
                "to_description",
                return_value=[vm],
            ),
            patch.object(
                validate_txns_from_batch.GeotagImagesFromVideo,
                "to_description",
                return_value=[_image_metadata(sample)],
            ) as mock_desc,
        ):
            geotag = GeotagImageSamplesFromVideo(source, num_processes=0)
            result = geotag.to_description([sample])
        assert len(result) == 1
        mock_desc.assert_called_once()
