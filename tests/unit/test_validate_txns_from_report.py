# Copyright (c) Meta Platforms, Inc. and affiliates.
#
# This source code is licensed under the BSD license found in the
# LICENSE file in the root directory of this source tree.

import xml.etree.ElementTree as ET
from unittest.mock import MagicMock, patch

from banking_tools import types
from banking_tools.compliance import validate_txns_from_report
from banking_tools.compliance.validate_txns_from_report import (
    GeotagImagesFromExifToolRunner,
    GeotagImagesFromExifToolWithSamples,
    GeotagImagesFromExifToolXML,
)
from banking_tools.compliance.txn_extractors.report import ImageExifToolExtractor


class TestBuildImageExtractors:
    def test_found_and_missing(self, tmp_path):
        found = tmp_path / "a.jpg"
        missing = tmp_path / "b.jpg"
        rdf_elem = ET.Element("rdf")
        with patch.object(
            validate_txns_from_report.report_reader,
            "canonical_path",
            side_effect=lambda p: str(p),
        ):
            rdf_by_path = {str(found): rdf_elem}
            results = GeotagImagesFromExifToolXML.build_txn_extractors(
                rdf_by_path, [found, missing]
            )
        assert isinstance(results[0], ImageExifToolExtractor)
        assert isinstance(results[1], types.ErrorMetadata)


class TestGeotagImagesFromExifToolXML:
    def test_generate_extractors(self, tmp_path):
        img = tmp_path / "a.jpg"
        geotag = GeotagImagesFromExifToolXML(tmp_path, num_processes=0)
        with patch.object(
            validate_txns_from_report.GeotagVideosFromExifToolXML,
            "find_rdf_by_path",
            return_value={},
        ):
            results = geotag._generate_txn_extractors([img])
        assert len(results) == 1
        assert isinstance(results[0], types.ErrorMetadata)


class TestGeotagImagesFromExifToolRunner:
    def test_exiftool_not_found(self, tmp_path):
        img = tmp_path / "a.jpg"
        runner = MagicMock()
        runner.extract_xml.side_effect = FileNotFoundError("no exiftool")
        runner._build_args_read_stdin.return_value = ["exiftool"]
        with (
            patch.object(
                validate_txns_from_report, "ExiftoolRunner", return_value=runner
            ),
            patch.object(validate_txns_from_report.constants, "EXIFTOOL_PATH", None),
        ):
            results = GeotagImagesFromExifToolRunner(
                num_processes=0
            )._generate_txn_extractors([img])
        assert isinstance(results[0], types.ErrorMetadata)

    def test_parse_error_yields_missing(self, tmp_path):
        img = tmp_path / "a.jpg"
        runner = MagicMock()
        runner.extract_xml.return_value = "<not valid"
        runner._build_args_read_stdin.return_value = ["exiftool"]
        with (
            patch.object(
                validate_txns_from_report, "ExiftoolRunner", return_value=runner
            ),
            patch.object(
                validate_txns_from_report.constants, "EXIFTOOL_PATH", "/bin/exiftool"
            ),
        ):
            results = GeotagImagesFromExifToolRunner(
                num_processes=0
            )._generate_txn_extractors([img])
        assert isinstance(results[0], types.ErrorMetadata)

    def test_success_path(self, tmp_path):
        img = tmp_path / "a.jpg"
        runner = MagicMock()
        runner.extract_xml.return_value = "<rdf></rdf>"
        runner._build_args_read_stdin.return_value = ["exiftool"]
        with (
            patch.object(
                validate_txns_from_report, "ExiftoolRunner", return_value=runner
            ),
            patch.object(
                validate_txns_from_report.constants, "EXIFTOOL_PATH", "/bin/exiftool"
            ),
            patch.object(
                validate_txns_from_report.report_reader,
                "index_rdf_description_by_path_from_xml_element",
                return_value={str(img): ET.Element("rdf")},
            ),
            patch.object(
                validate_txns_from_report.report_reader,
                "canonical_path",
                side_effect=lambda p: str(p),
            ),
        ):
            results = GeotagImagesFromExifToolRunner(
                num_processes=0
            )._generate_txn_extractors([img])
        assert isinstance(results[0], ImageExifToolExtractor)


class TestGeotagImagesFromExifToolWithSamples:
    def _img_md(self, path):
        return types.ImageMetadata(
            filename=path,
            lat=1.0,
            lon=2.0,
            alt=None,
            angle=None,
            time=0.0,
            MAPOrientation=1,
        )

    def test_to_description_combines_samples_and_non_samples(self, tmp_path):
        sample = tmp_path / "vid_000.jpg"
        other = tmp_path / "plain.jpg"
        geotag = GeotagImagesFromExifToolWithSamples(tmp_path, num_processes=0)
        with (
            patch.object(
                geotag, "compliance_samples", return_value=[self._img_md(sample)]
            ),
            patch.object(
                GeotagImagesFromExifToolXML,
                "to_description",
                return_value=[self._img_md(other)],
            ),
        ):
            result = geotag.to_description([sample, other])
        assert len(result) == 2

    def test_compliance_samples(self, tmp_path):
        video_path = tmp_path / "vid.mp4"
        sample = tmp_path / "vid_000.jpg"
        geotag = GeotagImagesFromExifToolWithSamples(tmp_path, num_processes=0)
        with (
            patch.object(
                validate_txns_from_report.GeotagVideosFromExifToolXML,
                "find_rdf_by_path",
                return_value={str(video_path): ET.Element("rdf")},
            ),
            patch.object(
                validate_txns_from_report.utils,
                "find_videos",
                return_value=[video_path],
            ),
            patch.object(
                validate_txns_from_report.utils,
                "find_all_image_samples",
                return_value={video_path: [sample]},
            ),
            patch.object(
                validate_txns_from_report.GeotagVideosFromExifToolXML,
                "to_description",
                return_value=[],
            ),
            patch.object(
                validate_txns_from_report.GeotagImagesFromVideo,
                "to_description",
                return_value=[self._img_md(sample)],
            ),
        ):
            result = geotag.compliance_samples([sample])
        assert len(result) == 1
