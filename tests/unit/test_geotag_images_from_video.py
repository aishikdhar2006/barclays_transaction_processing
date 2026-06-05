# Copyright (c) Meta Platforms, Inc. and affiliates.
#
# This source code is licensed under the BSD license found in the
# LICENSE file in the root directory of this source tree.

from pathlib import Path
from unittest.mock import patch

from banking_tools import types
from banking_tools.compliance import validate_txns_from_batch as vb
from banking_tools.compliance.validate_txns_from_batch import (
    GeotagImageSamplesFromVideo,
    GeotagImagesFromVideo,
)

MODULE = "banking_tools.compliance.validate_txns_from_batch"


def _image(name="s_0.jpg"):
    return types.ImageMetadata(
        time=0.0,
        lat=1.0,
        lon=2.0,
        alt=None,
        angle=None,
        filename=Path(f"/tmp/{name}"),
    )


def _video_md(path="/tmp/v.mp4", make="GoPro", model="H11"):
    return types.VideoMetadata(
        filename=Path(path),
        filetype=types.FileType.VIDEO,
        points=[],
        make=make,
        model=model,
        camera_uuid="uuid-1",
    )


def _video_err(path="/tmp/bad.mp4"):
    return types.ErrorMetadata(
        filename=Path(path),
        filetype=types.FileType.VIDEO,
        error=ValueError("no gps"),
    )


class TestGeotagImagesFromVideo:
    @patch(f"{MODULE}.utils.filter_video_samples")
    def test_error_video_propagates_to_samples(self, mock_filter):
        sample = Path("/tmp/bad_0.jpg")
        mock_filter.return_value = [sample]
        geotag = GeotagImagesFromVideo([_video_err()])
        result = geotag.to_description([sample])
        assert len(result) == 1
        assert isinstance(result[0], types.ErrorMetadata)
        assert result[0].filename == sample

    @patch.object(vb.GeotagImagesFromGPX, "to_description")
    @patch(f"{MODULE}.utils.filter_video_samples")
    def test_valid_video_sets_map_fields(self, mock_filter, mock_gpx):
        sample = Path("/tmp/s_0.jpg")
        mock_filter.return_value = [sample]
        img = _image("s_0.jpg")
        mock_gpx.return_value = [img]
        geotag = GeotagImagesFromVideo([_video_md()])
        result = geotag.to_description([sample])
        assert len(result) == 1
        assert result[0].MAPDeviceMake == "GoPro"
        assert result[0].MAPDeviceModel == "H11"
        assert result[0].MAPCameraUUID == "uuid-1"

    @patch.object(vb.GeotagImagesFromGPX, "to_description")
    @patch(f"{MODULE}.utils.filter_video_samples")
    def test_mixed_errors_and_valid(self, mock_filter, mock_gpx):
        err_sample = Path("/tmp/bad_0.jpg")
        ok_sample = Path("/tmp/s_0.jpg")
        mock_filter.side_effect = [[err_sample], [ok_sample]]
        mock_gpx.return_value = [_image("s_0.jpg")]
        geotag = GeotagImagesFromVideo([_video_err(), _video_md()])
        result = geotag.to_description([err_sample, ok_sample])
        kinds = sorted(type(m).__name__ for m in result)
        assert kinds == ["ErrorMetadata", "ImageMetadata"]


class TestGeotagImageSamplesFromVideo:
    @patch.object(vb.GeotagImagesFromVideo, "to_description")
    @patch(f"{MODULE}.GeotagVideosFromVideo")
    @patch(f"{MODULE}.utils.find_all_image_samples")
    @patch(f"{MODULE}.utils.find_videos")
    def test_pipeline(
        self, mock_find_videos, mock_find_samples, mock_geotag_videos, mock_final
    ):
        video_path = Path("/tmp/v.mp4")
        mock_find_videos.return_value = [video_path]
        mock_find_samples.return_value = {video_path: [Path("/tmp/s_0.jpg")]}
        mock_geotag_videos.return_value.to_description.return_value = [_video_md()]
        mock_final.return_value = [_image("s_0.jpg")]

        sampler = GeotagImageSamplesFromVideo(source_path=Path("/tmp"))
        result = sampler.to_description([Path("/tmp/s_0.jpg")])
        assert len(result) == 1
        mock_geotag_videos.return_value.to_description.assert_called_once_with(
            [video_path]
        )
