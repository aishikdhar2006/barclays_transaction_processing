# Copyright (c) Meta Platforms, Inc. and affiliates.
#
# This source code is licensed under the BSD license found in the
# LICENSE file in the root directory of this source tree.

import xml.etree.ElementTree as ET
from unittest.mock import MagicMock, patch

from banking_tools import types
from banking_tools.compliance import options, validate_batches_from_report
from banking_tools.compliance.validate_batches_from_report import (
    GeotagVideosFromExifToolRunner,
    GeotagVideosFromExifToolXML,
)
from banking_tools.compliance.batch_extractors.report import VideoExifToolExtractor


class TestBuildBatchExtractorsFromEtree:
    def test_found_and_missing(self, tmp_path):
        found = tmp_path / "a.mp4"
        missing = tmp_path / "b.mp4"
        with patch.object(
            validate_batches_from_report.report_reader,
            "canonical_path",
            side_effect=lambda p: str(p),
        ):
            rdf_by_path = {str(found): ET.Element("rdf")}
            results = GeotagVideosFromExifToolXML.build_batch_extractors_from_etree(
                rdf_by_path, [found, missing]
            )
        assert isinstance(results[0], VideoExifToolExtractor)
        assert isinstance(results[1], types.ErrorMetadata)


class TestFindRdfByPath:
    def test_source_path_branch(self, tmp_path):
        opt = options.SourcePathOption(source_path=tmp_path / "exif.xml")
        expected = {"x": ET.Element("rdf")}
        with patch.object(
            validate_batches_from_report,
            "index_rdf_description_by_path",
            return_value=expected,
        ):
            result = GeotagVideosFromExifToolXML.find_rdf_by_path(
                opt, [tmp_path / "v.mp4"]
            )
        assert result == expected

    def test_pattern_branch_skips_nonexistent(self, tmp_path):
        opt = options.SourcePathOption(pattern="/no/such/%f.xml")
        with patch.object(
            validate_batches_from_report.report_reader,
            "canonical_path",
            side_effect=lambda p: str(p),
        ):
            result = GeotagVideosFromExifToolXML.find_rdf_by_path(
                opt, [tmp_path / "v.mp4"]
            )
        assert result == {}

    def test_pattern_branch_matches(self, tmp_path):
        video = tmp_path / "v.mp4"
        xml_file = tmp_path / "v.xml"
        xml_file.write_text("<x/>")
        opt = options.SourcePathOption(pattern=str(tmp_path / "%f.xml"))
        rdf = ET.Element("rdf")
        with (
            patch.object(
                validate_batches_from_report.report_reader,
                "canonical_path",
                side_effect=lambda p: str(p),
            ),
            patch.object(
                validate_batches_from_report,
                "index_rdf_description_by_path",
                return_value={str(video): rdf},
            ),
            patch.object(options.SourcePathOption, "resolve", return_value=xml_file),
        ):
            result = GeotagVideosFromExifToolXML.find_rdf_by_path(opt, [video])
        assert result[str(video)] is rdf

    def test_generate_batch_extractors(self, tmp_path):
        opt = options.SourcePathOption(source_path=tmp_path / "exif.xml")
        geotag = GeotagVideosFromExifToolXML(opt, num_processes=0)
        with patch.object(
            GeotagVideosFromExifToolXML, "find_rdf_by_path", return_value={}
        ):
            results = geotag._generate_batch_extractors([tmp_path / "v.mp4"])
        assert isinstance(results[0], types.ErrorMetadata)


class TestGeotagVideosFromExifToolRunner:
    def test_exiftool_not_found(self, tmp_path):
        video = tmp_path / "v.mp4"
        runner = MagicMock()
        runner.extract_xml.side_effect = FileNotFoundError("no exiftool")
        runner._build_args_read_stdin.return_value = ["exiftool"]
        with (
            patch.object(
                validate_batches_from_report, "ExiftoolRunner", return_value=runner
            ),
            patch.object(validate_batches_from_report.constants, "EXIFTOOL_PATH", None),
        ):
            results = GeotagVideosFromExifToolRunner(
                num_processes=0
            )._generate_batch_extractors([video])
        assert isinstance(results[0], types.ErrorMetadata)

    def test_parse_error(self, tmp_path):
        video = tmp_path / "v.mp4"
        runner = MagicMock()
        runner.extract_xml.return_value = "<bad"
        runner._build_args_read_stdin.return_value = ["exiftool"]
        with (
            patch.object(
                validate_batches_from_report, "ExiftoolRunner", return_value=runner
            ),
            patch.object(
                validate_batches_from_report.constants, "EXIFTOOL_PATH", "/bin/exiftool"
            ),
        ):
            results = GeotagVideosFromExifToolRunner(
                num_processes=0
            )._generate_batch_extractors([video])
        assert isinstance(results[0], types.ErrorMetadata)

    def test_success(self, tmp_path):
        video = tmp_path / "v.mp4"
        runner = MagicMock()
        runner.extract_xml.return_value = "<rdf></rdf>"
        runner._build_args_read_stdin.return_value = ["exiftool"]
        with (
            patch.object(
                validate_batches_from_report, "ExiftoolRunner", return_value=runner
            ),
            patch.object(validate_batches_from_report.constants, "EXIFTOOL_PATH", None),
            patch.object(
                validate_batches_from_report.report_reader,
                "index_rdf_description_by_path_from_xml_element",
                return_value={str(video): ET.Element("rdf")},
            ),
            patch.object(
                validate_batches_from_report.report_reader,
                "canonical_path",
                side_effect=lambda p: str(p),
            ),
        ):
            results = GeotagVideosFromExifToolRunner(
                num_processes=0
            )._generate_batch_extractors([video])
        assert isinstance(results[0], VideoExifToolExtractor)
