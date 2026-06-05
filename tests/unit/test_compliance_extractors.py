# Copyright (c) Meta Platforms, Inc. and affiliates.
#
# This source code is licensed under the BSD license found in the
# LICENSE file in the root directory of this source tree.

import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from banking_tools import exceptions, types
from banking_tools.compliance.base import GeotagImagesFromGeneric
from banking_tools.compliance.txn_extractors.report import ImageExifToolExtractor
from banking_tools.compliance.txn_extractors.statement import ImageEXIFExtractor
from banking_tools.compliance.validate_txns_from_report import (
    GeotagImagesFromExifToolXML,
)
from banking_tools.report_reader import (
    EXIFTOOL_NAMESPACES,
    canonical_path,
    expand_tag,
)


def _make_rdf_element(tags: dict[str, str]) -> ET.Element:
    root = ET.Element(expand_tag("rdf:Description", EXIFTOOL_NAMESPACES))
    for ns_tag, value in tags.items():
        child = ET.SubElement(root, expand_tag(ns_tag, EXIFTOOL_NAMESPACES))
        child.text = value
    return root


def _geotagged_image(tmp_path: Path) -> tuple[Path, ET.Element]:
    image_path = tmp_path / "img.jpg"
    image_path.write_bytes(b"\xff\xd8\xff\xe0fakejpeg")
    element = _make_rdf_element(
        {
            "GPS:GPSLongitude": "10.0",
            "GPS:GPSLongitudeRef": "E",
            "GPS:GPSLatitude": "20.0",
            "GPS:GPSLatitudeRef": "N",
            "ExifIFD:DateTimeOriginal": "2021:07:15 15:37:30",
            "GPS:GPSAltitude": "100.0",
            "IFD0:Make": "Canon",
            "IFD0:Model": "EOS",
        }
    )
    return image_path, element


class TestImageExifToolExtractor:
    def test_extract_success(self, tmp_path):
        image_path, element = _geotagged_image(tmp_path)
        extractor = ImageExifToolExtractor(image_path, element)
        metadata = extractor.extract()
        assert isinstance(metadata, types.ImageMetadata)
        assert metadata.lon == 10.0
        assert metadata.lat == 20.0
        assert metadata.filename == image_path

    def test_extract_missing_lonlat_raises(self, tmp_path):
        image_path = tmp_path / "img.jpg"
        image_path.write_bytes(b"\xff\xd8\xff\xe0fakejpeg")
        element = _make_rdf_element({"ExifIFD:DateTimeOriginal": "2021:07:15 15:37:30"})
        extractor = ImageExifToolExtractor(image_path, element)
        with pytest.raises(exceptions.BankingPlatformGeoTaggingError):
            extractor.extract()

    def test_extract_missing_time_raises(self, tmp_path):
        image_path = tmp_path / "img.jpg"
        image_path.write_bytes(b"\xff\xd8\xff\xe0fakejpeg")
        element = _make_rdf_element(
            {
                "GPS:GPSLongitude": "10.0",
                "GPS:GPSLatitude": "20.0",
            }
        )
        extractor = ImageExifToolExtractor(image_path, element)
        with pytest.raises(exceptions.BankingPlatformGeoTaggingError):
            extractor.extract()


class TestImageEXIFExtractorSkipError:
    def test_skip_lonlat_error_defaults_zero(self, tmp_path):
        image_path = tmp_path / "img.jpg"
        image_path.write_bytes(b"\xff\xd8\xff\xe0fakejpeg")
        element = _make_rdf_element({"ExifIFD:DateTimeOriginal": "2021:07:15 15:37:30"})

        class _SkipExtractor(ImageExifToolExtractor):
            def __init__(self, image_path, element):
                ImageEXIFExtractor.__init__(self, image_path, skip_lonlat_error=True)
                self.element = element

        extractor = _SkipExtractor(image_path, element)
        metadata = extractor.extract()
        assert metadata.lon == 0.0
        assert metadata.lat == 0.0


class TestBuildTxnExtractors:
    def test_found_and_missing(self, tmp_path):
        image_path, element = _geotagged_image(tmp_path)
        missing_path = tmp_path / "missing.jpg"
        rdf_by_path = {canonical_path(image_path): element}

        results = GeotagImagesFromExifToolXML.build_txn_extractors(
            rdf_by_path, [image_path, missing_path]
        )
        assert len(results) == 2
        assert isinstance(results[0], ImageExifToolExtractor)
        assert isinstance(results[1], types.ErrorMetadata)


class TestRunExtraction:
    def test_run_extraction_success(self, tmp_path):
        image_path, element = _geotagged_image(tmp_path)
        extractor = ImageExifToolExtractor(image_path, element)
        result = GeotagImagesFromGeneric.run_extraction(extractor)
        assert isinstance(result, types.ImageMetadata)

    def test_run_extraction_description_error(self, tmp_path):
        image_path = tmp_path / "img.jpg"
        image_path.write_bytes(b"\xff\xd8\xff\xe0fakejpeg")
        element = _make_rdf_element({})
        extractor = ImageExifToolExtractor(image_path, element)
        result = GeotagImagesFromGeneric.run_extraction(extractor)
        assert isinstance(result, types.ErrorMetadata)


class TestToDescription:
    def test_to_description_serial(self, tmp_path):
        image_path, element = _geotagged_image(tmp_path)
        missing_path = tmp_path / "missing.jpg"

        class _Stub(GeotagImagesFromGeneric):
            def _generate_txn_extractors(self, image_paths):
                return GeotagImagesFromExifToolXML.build_txn_extractors(
                    {canonical_path(image_path): element}, image_paths
                )

        stub = _Stub(num_processes=0)
        results = stub.to_description([image_path, missing_path])
        assert len(results) == 2
        kinds = {type(r) for r in results}
        assert types.ImageMetadata in kinds
        assert types.ErrorMetadata in kinds
