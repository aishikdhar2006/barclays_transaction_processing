# Copyright (c) Meta Platforms, Inc. and affiliates.
#
# This source code is licensed under the BSD license found in the
# LICENSE file in the root directory of this source tree.

import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from banking_tools.report_reader import (
    EXIFTOOL_NAMESPACES,
    ExifToolRead,
    canonical_path,
    expand_tag,
    find_rdf_description_path,
    index_rdf_description_by_path_from_xml_element,
)


class TestExpandTag:
    def test_valid_tag(self):
        result = expand_tag("GPS:GPSLatitude", EXIFTOOL_NAMESPACES)
        assert result.startswith("{")
        assert "GPSLatitude" in result

    def test_invalid_tag_no_colon(self):
        with pytest.raises(ValueError, match="Invalid tag"):
            expand_tag("NoColonHere", EXIFTOOL_NAMESPACES)

    def test_unknown_namespace_raises(self):
        with pytest.raises(KeyError):
            expand_tag("Unknown:Tag", EXIFTOOL_NAMESPACES)


class TestCanonicalPath:
    def test_basic(self):
        result = canonical_path(Path("/tmp/test.jpg"))
        assert result == Path("/tmp/test.jpg").resolve().as_posix()

    def test_relative_resolves(self, tmp_path, monkeypatch):
        (tmp_path / "test.jpg").write_bytes(b"")
        monkeypatch.chdir(tmp_path)
        result = canonical_path(Path("test.jpg"))
        assert result == (tmp_path / "test.jpg").resolve().as_posix()
        assert result != "test.jpg"


class TestFindRdfDescriptionPath:
    def test_with_about_attr(self):
        tag = expand_tag("rdf:about", EXIFTOOL_NAMESPACES)
        elem = ET.Element("rdf:Description", {tag: "/tmp/test.jpg"})
        result = find_rdf_description_path(elem)
        assert result == Path("/tmp/test.jpg")

    def test_without_about_attr(self):
        elem = ET.Element("rdf:Description")
        result = find_rdf_description_path(elem)
        assert result is None


class TestIndexRdfDescriptionByPath:
    def test_with_descriptions(self):
        xml_str = """<?xml version="1.0" encoding="UTF-8"?>
<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
         xmlns:et="http://ns.exiftool.org/1.0/">
  <rdf:Description rdf:about="/tmp/test1.jpg">
  </rdf:Description>
  <rdf:Description rdf:about="/tmp/test2.jpg">
  </rdf:Description>
</rdf:RDF>"""
        root = ET.fromstring(xml_str)
        result = index_rdf_description_by_path_from_xml_element(root)
        assert len(result) == 2


class TestExifToolRead:
    def _make_xml(self, tags: dict[str, str]) -> ET.ElementTree:
        root = ET.Element("rdf:Description")
        for ns_tag, value in tags.items():
            expanded = expand_tag(ns_tag, EXIFTOOL_NAMESPACES)
            child = ET.SubElement(root, expanded)
            child.text = value
        tree = ET.ElementTree(root)
        return tree

    def test_extract_altitude_positive(self):
        tree = self._make_xml(
            {
                "GPS:GPSAltitude": "100.5",
                "GPS:GPSAltitudeRef": "0",
            }
        )
        reader = ExifToolRead(tree)
        alt = reader.extract_altitude()
        assert alt == 100.5

    def test_extract_altitude_below_sea(self):
        tree = self._make_xml(
            {
                "GPS:GPSAltitude": "50.0",
                "GPS:GPSAltitudeRef": "1",
            }
        )
        reader = ExifToolRead(tree)
        alt = reader.extract_altitude()
        assert alt == -50.0

    def test_extract_altitude_none(self):
        tree = self._make_xml({})
        reader = ExifToolRead(tree)
        alt = reader.extract_altitude()
        assert alt is None

    def test_extract_gps_datetime_none(self):
        tree = self._make_xml({})
        reader = ExifToolRead(tree)
        result = reader.extract_gps_datetime()
        assert result is None

    def test_extract_gps_datetime_from_xmp_none(self):
        tree = self._make_xml({})
        reader = ExifToolRead(tree)
        result = reader.extract_gps_datetime_from_xmp()
        assert result is None

    def test_extract_altitude_no_ref(self):
        tree = self._make_xml(
            {
                "GPS:GPSAltitude": "100.5",
            }
        )
        reader = ExifToolRead(tree)
        alt = reader.extract_altitude()
        assert alt == 100.5

    def test_extract_gps_datetime_with_data(self):
        tree = self._make_xml(
            {
                "GPS:GPSDateStamp": "2021:08:02",
                "GPS:GPSTimeStamp": "07:57:06",
            }
        )
        reader = ExifToolRead(tree)
        result = reader.extract_gps_datetime()
        assert result is not None
        assert result.year == 2021 and result.hour == 7

    def test_extract_gps_datetime_from_xmp_with_data(self):
        tree = self._make_xml(
            {
                "XMP-exif:GPSDateStamp": "2021:09:14",
                "XMP-exif:GPSDateTime": "08:23:56",
            }
        )
        reader = ExifToolRead(tree)
        result = reader.extract_gps_datetime_from_xmp()
        assert result is not None

    def test_extract_exif_datetime_from_xmp(self):
        tree = self._make_xml(
            {
                "XMP-exif:DateTimeOriginal": "2021:07:15 15:37:30",
            }
        )
        reader = ExifToolRead(tree)
        result = reader.extract_exif_datetime_from_xmp()
        assert result is not None
        assert result.hour == 15

    def test_extract_capture_time(self):
        tree = self._make_xml(
            {
                "GPS:GPSDateStamp": "2021:08:02",
                "GPS:GPSTimeStamp": "07:57:06",
            }
        )
        reader = ExifToolRead(tree)
        result = reader.extract_capture_time()
        assert result is not None

    def test_extract_capture_time_none(self):
        tree = self._make_xml({})
        reader = ExifToolRead(tree)
        assert reader.extract_capture_time() is None

    def test_extract_direction(self):
        tree = self._make_xml({"GPS:GPSImgDirection": "180.0"})
        reader = ExifToolRead(tree)
        assert reader.extract_direction() == 180.0

    def test_extract_direction_track_fallback(self):
        tree = self._make_xml({"GPS:GPSTrack": "90.0"})
        reader = ExifToolRead(tree)
        assert reader.extract_direction() == 90.0

    def test_extract_direction_none(self):
        tree = self._make_xml({})
        reader = ExifToolRead(tree)
        assert reader.extract_direction() is None

    def test_extract_lon_lat_basic(self):
        tree = self._make_xml(
            {
                "GPS:GPSLongitude": "10.0",
                "GPS:GPSLatitude": "20.0",
            }
        )
        reader = ExifToolRead(tree)
        assert reader.extract_lon_lat() == (10.0, 20.0)

    def test_extract_lon_lat_with_refs(self):
        tree = self._make_xml(
            {
                "GPS:GPSLongitude": "10.0",
                "GPS:GPSLongitudeRef": "W",
                "GPS:GPSLatitude": "20.0",
                "GPS:GPSLatitudeRef": "S",
            }
        )
        reader = ExifToolRead(tree)
        assert reader.extract_lon_lat() == (-10.0, -20.0)

    def test_extract_lon_lat_composite_fallback(self):
        tree = self._make_xml(
            {
                "Composite:GPSLongitude": "5.0",
                "Composite:GPSLatitude": "6.0",
            }
        )
        reader = ExifToolRead(tree)
        assert reader.extract_lon_lat() == (5.0, 6.0)

    def test_extract_lon_lat_none(self):
        tree = self._make_xml({})
        reader = ExifToolRead(tree)
        assert reader.extract_lon_lat() is None

    def test_extract_make(self):
        tree = self._make_xml({"IFD0:Make": "  Canon  "})
        reader = ExifToolRead(tree)
        assert reader.extract_make() == "Canon"

    def test_extract_make_none(self):
        tree = self._make_xml({})
        reader = ExifToolRead(tree)
        assert reader.extract_make() is None

    def test_extract_model(self):
        tree = self._make_xml({"IFD0:Model": " EOS 5D "})
        reader = ExifToolRead(tree)
        assert reader.extract_model() == "EOS 5D"

    def test_extract_model_gopro(self):
        tree = self._make_xml({"GoPro:Model": "HERO9"})
        reader = ExifToolRead(tree)
        assert reader.extract_model() == "HERO9"

    def test_extract_width(self):
        tree = self._make_xml({"File:ImageWidth": "1920"})
        reader = ExifToolRead(tree)
        assert reader.extract_width() == 1920

    def test_extract_height(self):
        tree = self._make_xml({"File:ImageHeight": "1080"})
        reader = ExifToolRead(tree)
        assert reader.extract_height() == 1080

    def test_extract_orientation_valid(self):
        tree = self._make_xml({"ExifIFD:Orientation": "6"})
        reader = ExifToolRead(tree)
        assert reader.extract_orientation() == 6

    def test_extract_orientation_default(self):
        tree = self._make_xml({})
        reader = ExifToolRead(tree)
        assert reader.extract_orientation() == 1

    def test_extract_orientation_out_of_range(self):
        tree = self._make_xml({"ExifIFD:Orientation": "99"})
        reader = ExifToolRead(tree)
        assert reader.extract_orientation() == 1

    def test_extract_camera_uuid_body_serial(self):
        tree = self._make_xml({"ExifIFD:BodySerialNumber": "ABC123"})
        reader = ExifToolRead(tree)
        result = reader.extract_camera_uuid()
        assert result is not None
        assert "ABC123" in result

    def test_extract_camera_uuid_none(self):
        tree = self._make_xml({})
        reader = ExifToolRead(tree)
        assert reader.extract_camera_uuid() is None
