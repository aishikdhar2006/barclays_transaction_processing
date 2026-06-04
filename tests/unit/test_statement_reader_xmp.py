# Copyright (c) Meta Platforms, Inc. and affiliates.
#
# This source code is licensed under the BSD license found in the
# LICENSE file in the root directory of this source tree.

import datetime
import xml.etree.ElementTree as et

import pytest

from banking_tools import statement_reader


def _build_xmp_tree(elements: dict) -> et.ElementTree:
    """Build an XMP tree with rdf:Description containing elements."""
    rdf_ns = statement_reader.XMP_NAMESPACES["rdf"]
    root = et.Element("root")
    desc = et.SubElement(root, f"{{{rdf_ns}}}Description")
    for ns_tag, value in elements.items():
        ns, tag = ns_tag.split(":")
        full_ns = statement_reader.XMP_NAMESPACES[ns]
        elem = et.SubElement(desc, f"{{{full_ns}}}{tag}")
        elem.text = str(value)
    return et.ElementTree(root)


def _build_xmp_tree_attrs(attrs: dict) -> et.ElementTree:
    """Build an XMP tree with rdf:Description attributes."""
    rdf_ns = statement_reader.XMP_NAMESPACES["rdf"]
    root = et.Element("root")
    attr_dict = {}
    for ns_tag, value in attrs.items():
        ns, tag = ns_tag.split(":")
        full_ns = statement_reader.XMP_NAMESPACES[ns]
        attr_dict[f"{{{full_ns}}}{tag}"] = str(value)
    et.SubElement(root, f"{{{rdf_ns}}}Description", attr_dict)
    return et.ElementTree(root)


class TestExifReadFromXMP:
    def test_extract_altitude(self):
        tree = _build_xmp_tree({"exif:GPSAltitude": "100.5"})
        reader = statement_reader.ExifReadFromXMP(tree)
        result = reader.extract_altitude()
        assert result == 100.5

    def test_extract_altitude_none(self):
        tree = _build_xmp_tree({})
        reader = statement_reader.ExifReadFromXMP(tree)
        result = reader.extract_altitude()
        assert result is None

    def test_extract_direction(self):
        tree = _build_xmp_tree({"exif:GPSImgDirection": "180.5"})
        reader = statement_reader.ExifReadFromXMP(tree)
        result = reader.extract_direction()
        assert result == 180.5

    def test_extract_direction_from_track(self):
        tree = _build_xmp_tree({"exif:GPSTrack": "90.0"})
        reader = statement_reader.ExifReadFromXMP(tree)
        result = reader.extract_direction()
        assert result == 90.0

    def test_extract_lon_lat(self):
        tree = _build_xmp_tree(
            {
                "exif:GPSLatitude": "40.7128",
                "exif:GPSLongitude": "-74.006",
            }
        )
        reader = statement_reader.ExifReadFromXMP(tree)
        result = reader.extract_lon_lat()
        assert result is not None
        assert result[1] == pytest.approx(40.7128, abs=0.001)
        assert result[0] == pytest.approx(-74.006, abs=0.001)

    def test_extract_lon_lat_with_ref(self):
        tree = _build_xmp_tree(
            {
                "exif:GPSLatitude": "40.7128",
                "exif:GPSLatitudeRef": "S",
                "exif:GPSLongitude": "74.006",
                "exif:GPSLongitudeRef": "W",
            }
        )
        reader = statement_reader.ExifReadFromXMP(tree)
        result = reader.extract_lon_lat()
        assert result is not None
        assert result[1] < 0  # South
        assert result[0] < 0  # West

    def test_extract_lon_lat_none(self):
        tree = _build_xmp_tree({})
        reader = statement_reader.ExifReadFromXMP(tree)
        result = reader.extract_lon_lat()
        assert result is None

    def test_extract_make(self):
        tree = _build_xmp_tree({"tiff:Make": "Canon"})
        reader = statement_reader.ExifReadFromXMP(tree)
        result = reader.extract_make()
        assert result == "Canon"

    def test_extract_model(self):
        tree = _build_xmp_tree({"tiff:Model": "EOS R5"})
        reader = statement_reader.ExifReadFromXMP(tree)
        result = reader.extract_model()
        assert result == "EOS R5"

    def test_extract_width(self):
        tree = _build_xmp_tree({"exif:PixelXDimension": "4000"})
        reader = statement_reader.ExifReadFromXMP(tree)
        result = reader.extract_width()
        assert result == 4000

    def test_extract_height(self):
        tree = _build_xmp_tree({"exif:PixelYDimension": "3000"})
        reader = statement_reader.ExifReadFromXMP(tree)
        result = reader.extract_height()
        assert result == 3000

    def test_extract_orientation_default(self):
        tree = _build_xmp_tree({})
        reader = statement_reader.ExifReadFromXMP(tree)
        result = reader.extract_orientation()
        assert result == 1

    def test_extract_orientation_valid(self):
        tree = _build_xmp_tree({"tiff:Orientation": "6"})
        reader = statement_reader.ExifReadFromXMP(tree)
        result = reader.extract_orientation()
        assert result == 6

    def test_extract_orientation_invalid(self):
        tree = _build_xmp_tree({"tiff:Orientation": "99"})
        reader = statement_reader.ExifReadFromXMP(tree)
        result = reader.extract_orientation()
        assert result == 1

    def test_extract_camera_uuid(self):
        tree = _build_xmp_tree({"exif:BodySerialNumber": "ABC123"})
        reader = statement_reader.ExifReadFromXMP(tree)
        result = reader.extract_camera_uuid()
        assert "ABC123" in result

    def test_extract_camera_uuid_lens_serial(self):
        tree = _build_xmp_tree({"exif:LensSerialNumber": "LENS456"})
        reader = statement_reader.ExifReadFromXMP(tree)
        result = reader.extract_camera_uuid()
        assert "LENS456" in result

    def test_extract_camera_uuid_none(self):
        tree = _build_xmp_tree({})
        reader = statement_reader.ExifReadFromXMP(tree)
        result = reader.extract_camera_uuid()
        assert result is None

    def test_extract_gps_datetime(self):
        tree = _build_xmp_tree(
            {
                "exif:GPSTimeStamp": "2021-07-15T05:37:30Z",
            }
        )
        reader = statement_reader.ExifReadFromXMP(tree)
        result = reader.extract_gps_datetime()
        assert result is not None
        assert result.year == 2021

    def test_extract_gps_datetime_with_date(self):
        tree = _build_xmp_tree(
            {
                "exif:GPSTimeStamp": "17:22:05.999000",
                "exif:GPSDateStamp": "2022:06:10",
            }
        )
        reader = statement_reader.ExifReadFromXMP(tree)
        result = reader.extract_gps_datetime()
        assert result is not None
        assert result.year == 2022

    def test_extract_gps_datetime_none(self):
        tree = _build_xmp_tree({})
        reader = statement_reader.ExifReadFromXMP(tree)
        result = reader.extract_gps_datetime()
        assert result is None

    def test_extract_exif_datetime(self):
        tree = _build_xmp_tree(
            {
                "exif:DateTimeOriginal": "2023:06:15 10:30:45",
            }
        )
        reader = statement_reader.ExifReadFromXMP(tree)
        result = reader.extract_exif_datetime()
        assert result is not None
        assert result.year == 2023

    def test_extract_exif_datetime_digitized(self):
        tree = _build_xmp_tree(
            {
                "exif:DateTimeDigitized": "2023:06:15 10:30:45",
            }
        )
        reader = statement_reader.ExifReadFromXMP(tree)
        result = reader.extract_exif_datetime()
        assert result is not None

    def test_extract_capture_time_prefers_gps(self):
        tree = _build_xmp_tree(
            {
                "exif:GPSTimeStamp": "2021-07-15T05:37:30Z",
                "exif:DateTimeOriginal": "2023:06:15 10:30:45",
            }
        )
        reader = statement_reader.ExifReadFromXMP(tree)
        result = reader.extract_capture_time()
        assert result is not None
        assert result.year == 2021

    def test_extract_capture_time_falls_back_to_exif(self):
        tree = _build_xmp_tree(
            {
                "exif:DateTimeOriginal": "2023:06:15 10:30:45",
            }
        )
        reader = statement_reader.ExifReadFromXMP(tree)
        result = reader.extract_capture_time()
        assert result is not None
        assert result.year == 2023

    def test_from_attrs(self):
        tree = _build_xmp_tree_attrs({"exif:GPSAltitude": "50.0"})
        reader = statement_reader.ExifReadFromXMP(tree)
        result = reader.extract_altitude()
        assert result == 50.0

    def test_extract_with_adobe_coord(self):
        tree = _build_xmp_tree(
            {
                "exif:GPSLatitude": "40,26.46N",
                "exif:GPSLongitude": "74,0.22W",
            }
        )
        reader = statement_reader.ExifReadFromXMP(tree)
        result = reader.extract_lon_lat()
        assert result is not None
        # Adobe format parsed
        assert result[1] > 0  # lat north
        assert result[0] < 0  # lon west


class TestParseDatetimestrWithSubsecAndOffset:
    def test_with_offset_negative(self):
        result = statement_reader.parse_datetimestr_with_subsec_and_offset(
            "2023:06:15 10:30:45", None, "-04:00"
        )
        assert result is not None
        assert result.tzinfo is not None

    def test_with_subsec_with_spaces(self):
        result = statement_reader.parse_datetimestr_with_subsec_and_offset(
            "2023:06:15 10:30:45", "12 ", None
        )
        assert result is not None
        # Space should be replaced with 0 → 120000 us

    def test_with_offset_time_format(self):
        result = statement_reader.parse_datetimestr_with_subsec_and_offset(
            "2023:06:15 10:30:45", None, "+05:30"
        )
        assert result is not None


class TestMakeValidTimezoneOffset:
    def test_normal_offset(self):
        delta = datetime.timedelta(hours=5, minutes=30)
        result = statement_reader.make_valid_timezone_offset(delta)
        assert result == delta

    def test_over_24_wraps(self):
        delta = datetime.timedelta(hours=25)
        result = statement_reader.make_valid_timezone_offset(delta)
        assert result < datetime.timedelta(hours=24)

    def test_under_neg24_wraps(self):
        delta = datetime.timedelta(hours=-25)
        result = statement_reader.make_valid_timezone_offset(delta)
        assert result > datetime.timedelta(hours=-24)


class TestExtractXmpEfficiently:
    def test_empty_file(self):
        import io

        fp = io.BytesIO(b"")
        result = statement_reader.extract_xmp_efficiently(fp)
        assert result is None

    def test_non_jpeg(self):
        import io

        fp = io.BytesIO(b"\x89PNG\r\n")
        result = statement_reader.extract_xmp_efficiently(fp)
        assert result is None

    def test_jpeg_without_xmp(self):
        import io

        # Valid JPEG SOI but no APP1
        fp = io.BytesIO(b"\xff\xd8\xff\xd9")
        result = statement_reader.extract_xmp_efficiently(fp)
        assert result is None

    def test_jpeg_with_xmp_app1(self):
        import io
        import struct

        xmp_xml = (
            b'<x:xmpmeta xmlns:x="adobe:ns:meta/">'
            b'<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"/>'
            b"</x:xmpmeta>"
        )
        identifier = b"http://ns.adobe.com/xap/1.0/\x00"
        payload = identifier + xmp_xml
        length = len(payload) + 2
        data = b"\xff\xd8" + b"\xff\xe1" + struct.pack(">H", length) + payload
        fp = io.BytesIO(data)
        result = statement_reader.extract_xmp_efficiently(fp)
        assert result is not None
        assert "xmpmeta" in result

    def test_jpeg_skips_non_xmp_app1(self):
        import io
        import struct

        # First APP1 is a non-XMP (EXIF) segment that should be skipped,
        # then EOF -> returns None
        exif_identifier = b"Exif\x00\x00"
        payload = exif_identifier + b"somedata"
        length = len(payload) + 2
        data = b"\xff\xd8" + b"\xff\xe1" + struct.pack(">H", length) + payload
        fp = io.BytesIO(data)
        result = statement_reader.extract_xmp_efficiently(fp)
        assert result is None

    def test_jpeg_skips_other_segment_then_finds_xmp(self):
        import io
        import struct

        # A non-APP1 segment (e.g. APP0/JFIF) followed by an XMP APP1 segment
        app0_payload = b"JFIF\x00data"
        app0 = b"\xff\xe0" + struct.pack(">H", len(app0_payload) + 2) + app0_payload

        identifier = b"http://ns.adobe.com/xap/1.0/\x00"
        xmp_xml = b"<x:xmpmeta>content</x:xmpmeta>"
        payload = identifier + xmp_xml
        app1 = b"\xff\xe1" + struct.pack(">H", len(payload) + 2) + payload

        data = b"\xff\xd8" + app0 + app1
        fp = io.BytesIO(data)
        result = statement_reader.extract_xmp_efficiently(fp)
        assert result is not None
        assert "content" in result
