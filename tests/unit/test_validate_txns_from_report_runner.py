# Copyright (c) Meta Platforms, Inc. and affiliates.
#
# This source code is licensed under the BSD license found in the
# LICENSE file in the root directory of this source tree.

import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import patch

from banking_tools import exceptions, report_reader, types
from banking_tools.compliance import validate_txns_from_report as vtr
from banking_tools.compliance.validate_txns_from_report import (
    GeotagImagesFromExifToolRunner,
    GeotagImagesFromExifToolXML,
)
from banking_tools.compliance.txn_extractors.report import ImageExifToolExtractor

MODULE = "banking_tools.compliance.validate_txns_from_report"


def _rdf():
    return ET.Element("rdf:Description")


class TestBuildTxnExtractors:
    def test_found_path(self):
        path = Path("/tmp/img.jpg")
        rdf_by_path = {report_reader.canonical_path(path): _rdf()}
        result = GeotagImagesFromExifToolXML.build_txn_extractors(rdf_by_path, [path])
        assert isinstance(result[0], ImageExifToolExtractor)

    def test_missing_path(self):
        result = GeotagImagesFromExifToolXML.build_txn_extractors(
            {}, [Path("/tmp/missing.jpg")]
        )
        assert isinstance(result[0], types.ErrorMetadata)
        assert isinstance(
            result[0].error,
            exceptions.BankingPlatformExifToolXMLNotFoundError,
        )


class TestRunnerGenerateExtractors:
    @patch(f"{MODULE}.ExiftoolRunner")
    def test_exiftool_not_found(self, mock_runner_cls):
        mock_runner_cls.return_value.extract_xml.side_effect = FileNotFoundError(
            "exiftool"
        )
        mock_runner_cls.return_value._build_args_read_stdin.return_value = ["x"]
        images = [Path("/tmp/a.jpg"), Path("/tmp/b.jpg")]
        with patch(f"{MODULE}.constants.EXIFTOOL_PATH", None):
            result = GeotagImagesFromExifToolRunner()._generate_txn_extractors(images)
        assert len(result) == 2
        assert all(
            isinstance(m.error, exceptions.BankingPlatformExiftoolNotFoundError)
            for m in result
        )

    @patch(f"{MODULE}.report_reader.index_rdf_description_by_path_from_xml_element")
    @patch(f"{MODULE}.ExiftoolRunner")
    def test_parse_error_yields_all_errors(self, mock_runner_cls, mock_index):
        mock_runner_cls.return_value.extract_xml.return_value = "<<<not xml"
        mock_runner_cls.return_value._build_args_read_stdin.return_value = ["x"]
        images = [Path("/tmp/a.jpg")]
        with patch(f"{MODULE}.constants.EXIFTOOL_PATH", None):
            result = GeotagImagesFromExifToolRunner()._generate_txn_extractors(images)
        # Empty rdf_by_path -> not-found error for the image
        assert isinstance(result[0], types.ErrorMetadata)
        mock_index.assert_not_called()

    @patch(f"{MODULE}.report_reader.index_rdf_description_by_path_from_xml_element")
    @patch(f"{MODULE}.ExiftoolRunner")
    def test_success_builds_extractor(self, mock_runner_cls, mock_index):
        path = Path("/tmp/a.jpg")
        mock_runner_cls.return_value.extract_xml.return_value = "<rdf/>"
        mock_runner_cls.return_value._build_args_read_stdin.return_value = ["x"]
        mock_index.return_value = {report_reader.canonical_path(path): _rdf()}
        with patch(f"{MODULE}.constants.EXIFTOOL_PATH", None):
            result = GeotagImagesFromExifToolRunner()._generate_txn_extractors([path])
        assert isinstance(result[0], ImageExifToolExtractor)
