# Copyright (c) Meta Platforms, Inc. and affiliates.
#
# This source code is licensed under the BSD license found in the
# LICENSE file in the root directory of this source tree.

import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import patch

import pytest

from banking_tools import exceptions, report_reader, types
from banking_tools.compliance import options
from banking_tools.compliance import validate_batches_from_report as vbr
from banking_tools.compliance.validate_batches_from_report import (
    GeotagVideosFromExifToolRunner,
    GeotagVideosFromExifToolXML,
)
from banking_tools.compliance.batch_extractors.report import VideoExifToolExtractor

MODULE = "banking_tools.compliance.validate_batches_from_report"


def _rdf_element():
    return ET.Element("rdf:Description")


class TestBuildBatchExtractorsFromEtree:
    def test_found_path_returns_extractor(self):
        path = Path("/tmp/video.mp4")
        rdf_by_path = {report_reader.canonical_path(path): _rdf_element()}
        result = GeotagVideosFromExifToolXML.build_batch_extractors_from_etree(
            rdf_by_path, [path]
        )
        assert len(result) == 1
        assert isinstance(result[0], VideoExifToolExtractor)

    def test_missing_path_returns_error(self):
        path = Path("/tmp/missing.mp4")
        result = GeotagVideosFromExifToolXML.build_batch_extractors_from_etree(
            {}, [path]
        )
        assert len(result) == 1
        assert isinstance(result[0], types.ErrorMetadata)
        assert isinstance(
            result[0].error,
            exceptions.BankingPlatformExifToolXMLNotFoundError,
        )

    def test_mixed(self):
        found = Path("/tmp/a.mp4")
        missing = Path("/tmp/b.mp4")
        rdf_by_path = {report_reader.canonical_path(found): _rdf_element()}
        result = GeotagVideosFromExifToolXML.build_batch_extractors_from_etree(
            rdf_by_path, [found, missing]
        )
        assert isinstance(result[0], VideoExifToolExtractor)
        assert isinstance(result[1], types.ErrorMetadata)


class TestFindRdfByPath:
    @patch(f"{MODULE}.index_rdf_description_by_path")
    def test_source_path(self, mock_index):
        mock_index.return_value = {"canon": _rdf_element()}
        opt = options.SourcePathOption(source_path=Path("/tmp/exif.xml"))
        result = GeotagVideosFromExifToolXML.find_rdf_by_path(opt, [])
        assert result == {"canon": mock_index.return_value["canon"]}
        mock_index.assert_called_once_with([Path("/tmp/exif.xml")])

    @patch(f"{MODULE}.index_rdf_description_by_path")
    def test_pattern_match(self, mock_index, tmp_path):
        video = tmp_path / "video.mp4"
        video.write_bytes(b"x")
        xml = tmp_path / "video.xml"
        xml.write_bytes(b"x")
        canon = report_reader.canonical_path(video)
        mock_index.return_value = {canon: _rdf_element()}
        opt = options.SourcePathOption(pattern=str(tmp_path / "%g.xml"))
        result = GeotagVideosFromExifToolXML.find_rdf_by_path(opt, [video])
        assert canon in result

    @patch(f"{MODULE}.index_rdf_description_by_path")
    def test_pattern_skips_nonexistent(self, mock_index, tmp_path):
        video = tmp_path / "video.mp4"
        opt = options.SourcePathOption(pattern=str(tmp_path / "nope_%g.xml"))
        result = GeotagVideosFromExifToolXML.find_rdf_by_path(opt, [video])
        assert result == {}
        mock_index.assert_not_called()


class TestGeotagVideosFromExifToolRunner:
    @patch(f"{MODULE}.ExiftoolRunner")
    def test_exiftool_not_found_returns_errors(self, mock_runner_cls):
        mock_runner_cls.return_value.extract_xml.side_effect = FileNotFoundError(
            "exiftool"
        )
        mock_runner_cls.return_value._build_args_read_stdin.return_value = ["x"]
        videos = [Path("/tmp/a.mp4"), Path("/tmp/b.mp4")]
        with patch(f"{MODULE}.constants.EXIFTOOL_PATH", None):
            result = GeotagVideosFromExifToolRunner()._generate_batch_extractors(videos)
        assert len(result) == 2
        assert all(isinstance(m, types.ErrorMetadata) for m in result)
        assert all(
            isinstance(m.error, exceptions.BankingPlatformExiftoolNotFoundError)
            for m in result
        )
