# Copyright (c) Meta Platforms, Inc. and affiliates.
#
# This source code is licensed under the BSD license found in the
# LICENSE file in the root directory of this source tree.

import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from banking_tools import report_reader


class TestExpandTag:
    def test_valid_tag(self):
        result = report_reader.expand_tag(
            "GPS:GPSAltitude", report_reader.EXIFTOOL_NAMESPACES
        )
        assert result == "{http://ns.exiftool.org/EXIF/GPS/1.0/}GPSAltitude"

    def test_valid_rdf_tag(self):
        result = report_reader.expand_tag(
            "rdf:Description", report_reader.EXIFTOOL_NAMESPACES
        )
        assert "http://www.w3.org/1999/02/22-rdf-syntax-ns#" in result

    def test_invalid_tag_no_colon(self):
        with pytest.raises(ValueError, match="Invalid tag"):
            report_reader.expand_tag("nocolon", report_reader.EXIFTOOL_NAMESPACES)


class TestCanonicalPath:
    def test_resolves_path(self, tmp_path):
        p = tmp_path / "subdir" / ".." / "file.jpg"
        result = report_reader.canonical_path(p)
        expected = str((tmp_path / "file.jpg").resolve().as_posix())
        assert result == expected


class TestFindRdfDescriptionPath:
    def test_with_about_attribute(self):
        tag = report_reader.expand_tag(
            "rdf:Description", report_reader.EXIFTOOL_NAMESPACES
        )
        about_tag = report_reader._EXPANDED_ABOUT_TAG
        elem = ET.Element(tag, {about_tag: "/path/to/image.jpg"})
        result = report_reader.find_rdf_description_path(elem)
        assert result == Path("/path/to/image.jpg")

    def test_without_about_attribute(self):
        tag = report_reader.expand_tag(
            "rdf:Description", report_reader.EXIFTOOL_NAMESPACES
        )
        elem = ET.Element(tag)
        result = report_reader.find_rdf_description_path(elem)
        assert result is None


class TestIndexRdfDescriptionByPath:
    def test_indexes_elements(self, tmp_path):
        # Create a simple XML with two rdf:Description elements
        rdf_ns = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
        about_tag = report_reader._EXPANDED_ABOUT_TAG

        root = ET.Element("root")
        desc_tag = f"{{{rdf_ns}}}Description"

        img1 = tmp_path / "img1.jpg"
        img1.touch()
        ET.SubElement(root, desc_tag, {about_tag: str(img1)})

        img2 = tmp_path / "img2.jpg"
        img2.touch()
        ET.SubElement(root, desc_tag, {about_tag: str(img2)})

        result = report_reader.index_rdf_description_by_path_from_xml_element(root)
        assert len(result) == 2
        assert report_reader.canonical_path(img1) in result
        assert report_reader.canonical_path(img2) in result


class TestExifToolRead:
    def _make_etree(self, elements: dict) -> ET.ElementTree:
        """Helper to build an XML tree with GPS and EXIF elements.

        ExifToolRead._extract_alternative_fields uses etree.findtext(field, namespaces=...)
        where field is like "GPS:GPSAltitude" and namespaces is EXIFTOOL_NAMESPACES.
        This means elements need to be at the root level using short namespace prefixes
        that are registered.
        """
        # Register namespaces so findtext works with prefix:tag
        for prefix, uri in report_reader.EXIFTOOL_NAMESPACES.items():
            ET.register_namespace(prefix, uri)

        root = ET.Element("root")
        for ns_tag, value in elements.items():
            expanded = report_reader.expand_tag(
                ns_tag, report_reader.EXIFTOOL_NAMESPACES
            )
            elem = ET.SubElement(root, expanded)
            elem.text = str(value)

        return ET.ElementTree(root)

    def test_extract_altitude_above_sea(self):
        etree = self._make_etree(
            {
                "GPS:GPSAltitude": "100.5",
                "GPS:GPSAltitudeRef": "0",
            }
        )
        reader = report_reader.ExifToolRead(etree)
        result = reader.extract_altitude()
        assert result == 100.5

    def test_extract_altitude_below_sea(self):
        etree = self._make_etree(
            {
                "GPS:GPSAltitude": "50.0",
                "GPS:GPSAltitudeRef": "1",
            }
        )
        reader = report_reader.ExifToolRead(etree)
        result = reader.extract_altitude()
        assert result == -50.0

    def test_extract_altitude_no_data(self):
        etree = self._make_etree({})
        reader = report_reader.ExifToolRead(etree)
        result = reader.extract_altitude()
        assert result is None

    def test_extract_gps_datetime(self):
        etree = self._make_etree(
            {
                "GPS:GPSDateStamp": "2023:06:15",
                "GPS:GPSTimeStamp": "10:30:45",
            }
        )
        reader = report_reader.ExifToolRead(etree)
        result = reader.extract_gps_datetime()
        assert result is not None
        assert result.year == 2023
        assert result.month == 6
        assert result.day == 15

    def test_extract_gps_datetime_missing(self):
        etree = self._make_etree({})
        reader = report_reader.ExifToolRead(etree)
        result = reader.extract_gps_datetime()
        assert result is None

    def test_extract_gps_datetime_from_xmp(self):
        etree = self._make_etree(
            {
                "XMP-exif:GPSDateStamp": "2021:09:14",
                "XMP-exif:GPSDateTime": "08:23:56.000000",
            }
        )
        reader = report_reader.ExifToolRead(etree)
        result = reader.extract_gps_datetime_from_xmp()
        assert result is not None
        assert result.year == 2021

    def test_extract_exif_datetime_from_xmp(self):
        etree = self._make_etree(
            {
                "XMP-exif:DateTimeOriginal": "2022:01:15 14:30:00",
            }
        )
        reader = report_reader.ExifToolRead(etree)
        result = reader.extract_exif_datetime_from_xmp()
        assert result is not None
        assert result.year == 2022

    def test_extract_exif_datetime_from_xmp_create_date(self):
        etree = self._make_etree(
            {
                "XMP-xmp:CreateDate": "2023:03:20 09:15:30",
            }
        )
        reader = report_reader.ExifToolRead(etree)
        result = reader.extract_exif_datetime_from_xmp()
        assert result is not None
        assert result.year == 2023

    def test_extract_exif_datetime_from_xmp_none(self):
        etree = self._make_etree({})
        reader = report_reader.ExifToolRead(etree)
        result = reader.extract_exif_datetime_from_xmp()
        assert result is None

    def test_extract_direction(self):
        etree = self._make_etree(
            {
                "GPS:GPSImgDirection": "180.5",
            }
        )
        reader = report_reader.ExifToolRead(etree)
        result = reader.extract_direction()
        assert result == 180.5

    def test_extract_lon_lat(self):
        etree = self._make_etree(
            {
                "GPS:GPSLongitude": "10.5",
                "GPS:GPSLatitude": "20.5",
            }
        )
        reader = report_reader.ExifToolRead(etree)
        result = reader.extract_lon_lat()
        assert result == (10.5, 20.5)

    def test_extract_lon_lat_west_south(self):
        etree = self._make_etree(
            {
                "GPS:GPSLongitude": "10.5",
                "GPS:GPSLongitudeRef": "W",
                "GPS:GPSLatitude": "20.5",
                "GPS:GPSLatitudeRef": "S",
            }
        )
        reader = report_reader.ExifToolRead(etree)
        result = reader.extract_lon_lat()
        assert result == (-10.5, -20.5)

    def test_extract_make(self):
        etree = self._make_etree(
            {
                "IFD0:Make": " Canon ",
            }
        )
        reader = report_reader.ExifToolRead(etree)
        result = reader.extract_make()
        assert result == "Canon"

    def test_extract_model(self):
        etree = self._make_etree(
            {
                "IFD0:Model": " EOS R5 ",
            }
        )
        reader = report_reader.ExifToolRead(etree)
        result = reader.extract_model()
        assert result == "EOS R5"

    def test_extract_width(self):
        etree = self._make_etree(
            {
                "File:ImageWidth": "4000",
            }
        )
        reader = report_reader.ExifToolRead(etree)
        result = reader.extract_width()
        assert result == 4000

    def test_extract_height(self):
        etree = self._make_etree(
            {
                "File:ImageHeight": "3000",
            }
        )
        reader = report_reader.ExifToolRead(etree)
        result = reader.extract_height()
        assert result == 3000

    def test_extract_orientation_default(self):
        etree = self._make_etree({})
        reader = report_reader.ExifToolRead(etree)
        result = reader.extract_orientation()
        assert result == 1

    def test_extract_orientation_valid(self):
        etree = self._make_etree(
            {
                "IFD0:Orientation": "6",
            }
        )
        reader = report_reader.ExifToolRead(etree)
        result = reader.extract_orientation()
        assert result == 6

    def test_extract_orientation_invalid(self):
        etree = self._make_etree(
            {
                "IFD0:Orientation": "99",
            }
        )
        reader = report_reader.ExifToolRead(etree)
        result = reader.extract_orientation()
        assert result == 1

    def test_extract_camera_uuid(self):
        etree = self._make_etree(
            {
                "ExifIFD:BodySerialNumber": "ABC123",
            }
        )
        reader = report_reader.ExifToolRead(etree)
        result = reader.extract_camera_uuid()
        assert "ABC123" in result

    def test_extract_camera_uuid_none(self):
        etree = self._make_etree({})
        reader = report_reader.ExifToolRead(etree)
        result = reader.extract_camera_uuid()
        assert result is None

    def test_extract_exif_datetime_original(self):
        etree = self._make_etree(
            {
                "ExifIFD:DateTimeOriginal": "2022:05:10 08:00:00",
            }
        )
        reader = report_reader.ExifToolRead(etree)
        result = reader.extract_exif_datetime()
        assert result is not None
        assert result.year == 2022
        assert result.month == 5

    def test_extract_exif_datetime_create_date_fallback(self):
        etree = self._make_etree(
            {
                "ExifIFD:CreateDate": "2021:04:09 07:00:00",
            }
        )
        reader = report_reader.ExifToolRead(etree)
        result = reader.extract_exif_datetime()
        assert result is not None
        assert result.year == 2021

    def test_extract_exif_datetime_modify_date_fallback(self):
        etree = self._make_etree(
            {
                "IFD0:ModifyDate": "2020:03:08 06:00:00",
            }
        )
        reader = report_reader.ExifToolRead(etree)
        result = reader.extract_exif_datetime()
        assert result is not None
        assert result.year == 2020

    def test_extract_exif_datetime_none(self):
        etree = self._make_etree({})
        reader = report_reader.ExifToolRead(etree)
        assert reader.extract_exif_datetime() is None

    def test_extract_capture_time_prefers_gps(self):
        etree = self._make_etree(
            {
                "GPS:GPSDateStamp": "2023:06:15",
                "GPS:GPSTimeStamp": "10:30:45",
                "ExifIFD:DateTimeOriginal": "2000:01:01 00:00:00",
            }
        )
        reader = report_reader.ExifToolRead(etree)
        result = reader.extract_capture_time()
        assert result is not None
        assert result.year == 2023

    def test_extract_capture_time_falls_back_to_exif(self):
        etree = self._make_etree(
            {
                "ExifIFD:DateTimeOriginal": "2019:02:07 05:00:00",
            }
        )
        reader = report_reader.ExifToolRead(etree)
        result = reader.extract_capture_time()
        assert result is not None
        assert result.year == 2019

    def test_extract_capture_time_none(self):
        etree = self._make_etree({})
        reader = report_reader.ExifToolRead(etree)
        assert reader.extract_capture_time() is None
