# Copyright (c) Meta Platforms, Inc. and affiliates.
#
# This source code is licensed under the BSD license found in the
# LICENSE file in the root directory of this source tree.

from pathlib import Path
from unittest.mock import patch

import pytest

from banking_tools import exceptions, process_compliance_properties, types
from banking_tools.compliance.options import (
    SourceType,
)


class TestNormalizeImportPaths:
    def test_single_path(self, tmp_path):
        result = process_compliance_properties._normalize_import_paths(tmp_path)
        assert result == [tmp_path]

    def test_list_of_paths(self, tmp_path):
        p1 = tmp_path / "a"
        p2 = tmp_path / "b"
        result = process_compliance_properties._normalize_import_paths([p1, p2])
        assert len(result) == 2

    def test_deduplicate(self, tmp_path):
        result = process_compliance_properties._normalize_import_paths(
            [tmp_path, tmp_path]
        )
        assert len(result) == 1


class TestParseSourceOptions:
    def test_basic_source(self):
        result = process_compliance_properties._parse_source_options(
            geotag_source=["native"],
            video_geotag_source=[],
            geotag_source_path=None,
        )
        assert len(result) >= 1
        assert result[0].source == SourceType.NATIVE

    def test_with_video_source(self):
        result = process_compliance_properties._parse_source_options(
            geotag_source=[],
            video_geotag_source=["gopro"],
            geotag_source_path=None,
        )
        assert len(result) >= 1
        # Video source should have filetypes set to VIDEO
        assert result[0].filetypes is not None
        assert types.FileType.VIDEO in result[0].filetypes

    def test_with_source_path(self, tmp_path):
        result = process_compliance_properties._parse_source_options(
            geotag_source=["native"],
            video_geotag_source=[],
            geotag_source_path=tmp_path,
        )
        assert result[0].source_path is not None
        assert result[0].source_path.source_path == tmp_path


class TestProcessComplianceProperties:
    def test_nonexistent_path_raises(self, tmp_path):
        fake = tmp_path / "nonexistent"
        with pytest.raises(exceptions.BankingPlatformFileNotFoundError):
            process_compliance_properties.process_compliance_properties(
                import_path=fake,
                filetypes=None,
                geotag_source=["native"],
                geotag_source_path=None,
                video_geotag_source=[],
            )

    @patch("banking_tools.process_compliance_properties.process")
    @patch("banking_tools.process_compliance_properties.utils.find_videos")
    @patch("banking_tools.process_compliance_properties.utils.find_images")
    def test_empty_directory(
        self, mock_find_images, mock_find_videos, mock_process, tmp_path
    ):
        mock_find_images.return_value = []
        mock_find_videos.return_value = []
        mock_process.return_value = []

        result = process_compliance_properties.process_compliance_properties(
            import_path=tmp_path,
            filetypes=None,
            geotag_source=["native"],
            geotag_source_path=None,
            video_geotag_source=[],
        )
        assert result == []

    @patch("banking_tools.process_compliance_properties.process")
    @patch("banking_tools.process_compliance_properties.utils.find_videos")
    @patch("banking_tools.process_compliance_properties.utils.find_images")
    def test_default_sources(
        self, mock_find_images, mock_find_videos, mock_process, tmp_path
    ):
        mock_find_images.return_value = []
        mock_find_videos.return_value = []
        mock_process.return_value = []

        process_compliance_properties.process_compliance_properties(
            import_path=tmp_path,
            filetypes=None,
            geotag_source=[],
            geotag_source_path=None,
            video_geotag_source=[],
        )
        # Should use DEFAULT_GEOTAG_SOURCE_OPTIONS
        mock_process.assert_called_once()


class TestApplyOffsets:
    def test_offset_time(self):
        metadata = types.ImageMetadata(
            filename=Path("/test.jpg"),
            lat=40.0,
            lon=-74.0,
            alt=None,
            angle=None,
            time=100.0,
            MAPOrientation=1,
        )
        process_compliance_properties._apply_offsets([metadata], offset_time=10.0)
        assert metadata.time == 110.0

    def test_offset_angle(self):
        metadata = types.ImageMetadata(
            filename=Path("/test.jpg"),
            lat=40.0,
            lon=-74.0,
            alt=None,
            angle=90.0,
            time=100.0,
            MAPOrientation=1,
        )
        process_compliance_properties._apply_offsets([metadata], offset_angle=45.0)
        assert metadata.angle == 135.0

    def test_offset_angle_wraps(self):
        metadata = types.ImageMetadata(
            filename=Path("/test.jpg"),
            lat=40.0,
            lon=-74.0,
            alt=None,
            angle=350.0,
            time=100.0,
            MAPOrientation=1,
        )
        process_compliance_properties._apply_offsets([metadata], offset_angle=20.0)
        assert metadata.angle == 10.0

    def test_none_angle_gets_set(self):
        metadata = types.ImageMetadata(
            filename=Path("/test.jpg"),
            lat=40.0,
            lon=-74.0,
            alt=None,
            angle=None,
            time=100.0,
            MAPOrientation=1,
        )
        process_compliance_properties._apply_offsets([metadata], offset_angle=45.0)
        assert metadata.angle == 45.0
