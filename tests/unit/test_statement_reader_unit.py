# Copyright (c) Meta Platforms, Inc. and affiliates.
#
# This source code is licensed under the BSD license found in the
# LICENSE file in the root directory of this source tree.

import datetime
import io
import xml.etree.ElementTree as ET

from exifread.utils import Ratio

from banking_tools import statement_reader as sr
from banking_tools.statement_reader import ExifRead, ExifReadFromXMP, XMP_NAMESPACES


def _make_xmp_reader(tags: dict[str, str]) -> ExifReadFromXMP:
    """Build an ExifReadFromXMP from a dict of prefixed tag -> value (as elements)."""
    rdf_ns = XMP_NAMESPACES["rdf"]
    xml = '<?xml version="1.0"?>\n<x:xmpmeta xmlns:x="adobe:ns:meta/">\n'
    xml += f'<rdf:RDF xmlns:rdf="{rdf_ns}"'
    for prefix, uri in XMP_NAMESPACES.items():
        if prefix in ("rdf", "x"):
            continue
        xml += f' xmlns:{prefix}="{uri}"'
    xml += ">\n<rdf:Description>\n"
    for key, value in tags.items():
        xml += f"<{key}>{value}</{key}>\n"
    xml += "</rdf:Description>\n</rdf:RDF>\n</x:xmpmeta>"
    etree = ET.ElementTree(ET.fromstring(xml))
    return ExifReadFromXMP(etree)


class TestEvalFrac:
    def test_basic(self):
        assert sr.eval_frac(Ratio(1, 2)) == 0.5

    def test_whole(self):
        assert sr.eval_frac(Ratio(10, 1)) == 10.0


class TestGpsToDecimal:
    def test_basic(self):
        result = sr.gps_to_decimal((Ratio(30, 1), Ratio(30, 1), Ratio(0, 1)))
        assert result == 30.5

    def test_with_seconds(self):
        result = sr.gps_to_decimal((Ratio(10, 1), Ratio(0, 1), Ratio(3600, 1)))
        assert result == 11.0

    def test_non_ratio_deg(self):
        assert sr.gps_to_decimal((1, Ratio(0, 1), Ratio(0, 1))) is None

    def test_non_ratio_min(self):
        assert sr.gps_to_decimal((Ratio(1, 1), 0, Ratio(0, 1))) is None

    def test_non_ratio_sec(self):
        assert sr.gps_to_decimal((Ratio(1, 1), Ratio(0, 1), 0)) is None

    def test_too_few(self):
        assert sr.gps_to_decimal((Ratio(1, 1),)) is None

    def test_zero_division(self):
        assert sr.gps_to_decimal((Ratio(1, 0), Ratio(0, 1), Ratio(0, 1))) is None


class TestParseCoordNumeric:
    def test_north(self):
        assert sr._parse_coord_numeric("30.5", "N") == 30.5

    def test_south_negative(self):
        assert sr._parse_coord_numeric("30.5", "S") == -30.5

    def test_no_ref(self):
        assert sr._parse_coord_numeric("30.5", None) == 30.5

    def test_invalid_value(self):
        assert sr._parse_coord_numeric("abc", "N") is None

    def test_invalid_ref(self):
        assert sr._parse_coord_numeric("30.5", "X") is None


class TestParseCoordAdobe:
    def test_valid(self):
        result = sr._parse_coord_adobe("30,30.0N")
        assert result == 30.5

    def test_west_negative(self):
        result = sr._parse_coord_adobe("30,30.0W")
        assert result == -30.5

    def test_invalid(self):
        assert sr._parse_coord_adobe("not a coord") is None


class TestParseCoord:
    def test_none(self):
        assert sr._parse_coord(None, "N") is None

    def test_numeric(self):
        assert sr._parse_coord("12.0", "N") == 12.0

    def test_adobe_fallback(self):
        assert sr._parse_coord("30,30.0N", None) == 30.5


class TestParseIso:
    def test_basic(self):
        dt = sr._parse_iso("2021-08-02T07:57:06")
        assert dt is not None
        assert dt.year == 2021 and dt.hour == 7

    def test_with_z(self):
        dt = sr._parse_iso("2021-08-02T07:57:06Z")
        assert dt is not None
        assert dt.tzinfo is not None

    def test_invalid(self):
        assert sr._parse_iso("garbage") is None


class TestStrptimeAlternativeFormats:
    def test_matches_format(self):
        dt = sr.strptime_alternative_formats("2021:08:02", ["%Y:%m:%d"])
        assert dt is not None and dt.year == 2021

    def test_iso_branch(self):
        dt = sr.strptime_alternative_formats("2021-08-02T07:57:06", ["ISO"])
        assert dt is not None

    def test_no_match(self):
        assert sr.strptime_alternative_formats("xyz", ["%Y:%m:%d"]) is None


class TestParseTimestrAsTimedelta:
    def test_full(self):
        td = sr.parse_timestr_as_timedelta("01:02:03")
        assert td == datetime.timedelta(hours=1, minutes=2, seconds=3)

    def test_hours_minutes(self):
        td = sr.parse_timestr_as_timedelta("01:30")
        assert td == datetime.timedelta(hours=1, minutes=30)

    def test_hours_only(self):
        td = sr.parse_timestr_as_timedelta("05")
        assert td == datetime.timedelta(hours=5)

    def test_invalid(self):
        assert sr.parse_timestr_as_timedelta("aa:bb") is None


class TestParseTimeRatiosAsTimedelta:
    def test_basic(self):
        td = sr.parse_time_ratios_as_timedelta([Ratio(1, 1), Ratio(2, 1), Ratio(3, 1)])
        assert td == datetime.timedelta(hours=1, minutes=2, seconds=3)

    def test_too_few(self):
        assert sr.parse_time_ratios_as_timedelta([Ratio(1, 1)]) is None

    def test_non_ratio(self):
        assert sr.parse_time_ratios_as_timedelta([1, 2, 3]) is None

    def test_zero_division(self):
        assert (
            sr.parse_time_ratios_as_timedelta([Ratio(1, 0), Ratio(2, 1), Ratio(3, 1)])
            is None
        )


class TestParseGpsDatetime:
    def test_iso(self):
        dt = sr.parse_gps_datetime("2021-08-02T07:57:06")
        assert dt is not None
        assert dt.tzinfo == datetime.timezone.utc

    def test_iso_with_tz_preserved(self):
        dt = sr.parse_gps_datetime("2021-08-02T07:57:06+02:00")
        assert dt is not None
        assert dt.utcoffset() == datetime.timedelta(hours=2)

    def test_separate_date_time(self):
        dt = sr.parse_gps_datetime("2021:08:02 07:57:06")
        assert dt is not None
        assert dt.year == 2021 and dt.hour == 7

    def test_invalid_single_part(self):
        assert sr.parse_gps_datetime("2021:08:02") is None


class TestParseGpsDatetimeSeparately:
    def test_basic(self):
        dt = sr.parse_gps_datetime_separately("2021:08:02", "07:57:06")
        assert dt is not None
        assert dt.tzinfo == datetime.timezone.utc

    def test_with_z(self):
        dt = sr.parse_gps_datetime_separately("2021:08:02", "07:57:06Z")
        assert dt is not None
        assert dt.tzinfo == datetime.timezone.utc

    def test_with_offset(self):
        dt = sr.parse_gps_datetime_separately("2021:08:02", "07:57:06+01:00")
        assert dt is not None
        assert dt.utcoffset() == datetime.timedelta(hours=1)

    def test_with_negative_offset(self):
        dt = sr.parse_gps_datetime_separately("2021:08:02", "07:57:06-05:00")
        assert dt is not None
        assert dt.utcoffset() == datetime.timedelta(hours=-5)

    def test_invalid_date(self):
        assert sr.parse_gps_datetime_separately("notadate", "07:57:06") is None

    def test_invalid_time(self):
        assert sr.parse_gps_datetime_separately("2021:08:02", "aa:bb:cc") is None


class TestParseDatetimestrWithSubsecAndOffset:
    def test_basic(self):
        dt = sr.parse_datetimestr_with_subsec_and_offset("2021:07:15 15:37:30")
        assert dt is not None
        assert dt.hour == 15

    def test_with_subsec(self):
        dt = sr.parse_datetimestr_with_subsec_and_offset(
            "2021:07:15 15:37:30", subsec="123"
        )
        assert dt is not None
        assert dt.microsecond == 123000

    def test_with_positive_offset(self):
        dt = sr.parse_datetimestr_with_subsec_and_offset(
            "2021:07:15 15:37:30", tz_offset="+02:00"
        )
        assert dt is not None
        assert dt.utcoffset() == datetime.timedelta(hours=2)

    def test_with_negative_offset(self):
        dt = sr.parse_datetimestr_with_subsec_and_offset(
            "2021:07:15 15:37:30", tz_offset="-03:00"
        )
        assert dt is not None
        assert dt.utcoffset() == datetime.timedelta(hours=-3)

    def test_invalid(self):
        assert sr.parse_datetimestr_with_subsec_and_offset("garbage") is None


class TestMakeValidTimezoneOffset:
    def test_within_range(self):
        d = datetime.timedelta(hours=5)
        assert sr.make_valid_timezone_offset(d) == d

    def test_over_24h(self):
        d = datetime.timedelta(hours=25)
        result = sr.make_valid_timezone_offset(d)
        assert result == datetime.timedelta(hours=1)

    def test_under_negative_24h(self):
        d = datetime.timedelta(hours=-25)
        result = sr.make_valid_timezone_offset(d)
        assert result == datetime.timedelta(hours=-1)


class TestExifReadFromXMP:
    def test_extract_altitude(self):
        reader = _make_xmp_reader({"exif:GPSAltitude": "123.4"})
        assert reader.extract_altitude() == 123.4

    def test_extract_altitude_none(self):
        reader = _make_xmp_reader({})
        assert reader.extract_altitude() is None

    def test_extract_exif_datetime_original(self):
        reader = _make_xmp_reader({"exif:DateTimeOriginal": "2021:07:15 15:37:30"})
        dt = reader.extract_exif_datetime()
        assert dt is not None and dt.hour == 15

    def test_extract_exif_datetime_digitized_fallback(self):
        reader = _make_xmp_reader({"exif:DateTimeDigitized": "2021:07:15 16:00:00"})
        dt = reader.extract_exif_datetime()
        assert dt is not None and dt.hour == 16

    def test_extract_exif_datetime_none(self):
        reader = _make_xmp_reader({})
        assert reader.extract_exif_datetime() is None

    def test_extract_gps_datetime_iso(self):
        reader = _make_xmp_reader({"exif:GPSTimeStamp": "2021-07-15T05:37:30Z"})
        dt = reader.extract_gps_datetime()
        assert dt is not None

    def test_extract_gps_datetime_separate(self):
        reader = _make_xmp_reader(
            {
                "exif:GPSTimeStamp": "17:22:05",
                "exif:GPSDateStamp": "2021:07:15",
            }
        )
        dt = reader.extract_gps_datetime()
        assert dt is not None

    def test_extract_gps_datetime_none(self):
        reader = _make_xmp_reader({})
        assert reader.extract_gps_datetime() is None

    def test_extract_capture_time_from_exif(self):
        reader = _make_xmp_reader({"exif:DateTimeOriginal": "2021:07:15 15:37:30"})
        assert reader.extract_capture_time() is not None

    def test_extract_direction(self):
        reader = _make_xmp_reader({"exif:GPSImgDirection": "270.0"})
        assert reader.extract_direction() == 270.0

    def test_extract_lon_lat(self):
        reader = _make_xmp_reader(
            {
                "exif:GPSLatitude": "20.0",
                "exif:GPSLatitudeRef": "N",
                "exif:GPSLongitude": "10.0",
                "exif:GPSLongitudeRef": "E",
            }
        )
        assert reader.extract_lon_lat() == (10.0, 20.0)

    def test_extract_lon_lat_none(self):
        reader = _make_xmp_reader({})
        assert reader.extract_lon_lat() is None

    def test_extract_make(self):
        reader = _make_xmp_reader({"tiff:Make": " Canon "})
        assert reader.extract_make() == "Canon"

    def test_extract_model(self):
        reader = _make_xmp_reader({"tiff:Model": " EOS "})
        assert reader.extract_model() == "EOS"

    def test_extract_width(self):
        reader = _make_xmp_reader({"exif:PixelXDimension": "1920"})
        assert reader.extract_width() == 1920

    def test_extract_height(self):
        reader = _make_xmp_reader({"exif:PixelYDimension": "1080"})
        assert reader.extract_height() == 1080

    def test_extract_orientation(self):
        reader = _make_xmp_reader({"tiff:Orientation": "6"})
        assert reader.extract_orientation() == 6

    def test_extract_orientation_default(self):
        reader = _make_xmp_reader({})
        assert reader.extract_orientation() == 1


def _layered_reader(xmp_tags: dict[str, str] | None) -> ExifRead:
    """ExifRead over an empty EXIF stream with a pre-seeded XMP fallback."""
    reader = ExifRead(io.BytesIO(b""))
    reader._xml_extracted = True
    reader._cached_xml = _make_xmp_reader(xmp_tags) if xmp_tags is not None else None
    return reader


class TestExifReadLayered:
    def test_altitude_falls_back_to_xmp(self):
        reader = _layered_reader({"exif:GPSAltitude": "55.5"})
        assert reader.extract_altitude() == 55.5

    def test_capture_time_falls_back_to_xmp(self):
        reader = _layered_reader({"exif:DateTimeOriginal": "2021:07:15 15:37:30"})
        assert reader.extract_capture_time() is not None

    def test_lon_lat_falls_back_to_xmp(self):
        reader = _layered_reader(
            {
                "exif:GPSLatitude": "20.0",
                "exif:GPSLatitudeRef": "N",
                "exif:GPSLongitude": "10.0",
                "exif:GPSLongitudeRef": "E",
            }
        )
        assert reader.extract_lon_lat() == (10.0, 20.0)

    def test_make_model_fall_back_to_xmp(self):
        reader = _layered_reader({"tiff:Make": "Canon", "tiff:Model": "EOS"})
        assert reader.extract_make() == "Canon"
        assert reader.extract_model() == "EOS"

    def test_width_height_fall_back_to_xmp(self):
        reader = _layered_reader(
            {"exif:PixelXDimension": "1920", "exif:PixelYDimension": "1080"}
        )
        assert reader.extract_width() == 1920
        assert reader.extract_height() == 1080

    def test_returns_none_when_no_xmp(self):
        reader = _layered_reader(None)
        assert reader.extract_altitude() is None
        assert reader.extract_capture_time() is None
        assert reader.extract_lon_lat() is None
        assert reader.extract_make() is None
        assert reader.extract_model() is None
        assert reader.extract_width() is None
        assert reader.extract_height() is None

    def test_extract_xmp_no_data_returns_none(self):
        reader = ExifRead(io.BytesIO(b""))
        assert reader._extract_xmp() is None
