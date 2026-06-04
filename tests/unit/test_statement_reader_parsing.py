# Copyright (c) Meta Platforms, Inc. and affiliates.
#
# This source code is licensed under the BSD license found in the
# LICENSE file in the root directory of this source tree.

import datetime

import pytest
from exifread.utils import Ratio

from banking_tools import statement_reader


class TestEvalFrac:
    def test_normal(self):
        assert statement_reader.eval_frac(Ratio(10, 2)) == 5.0

    def test_zero_num(self):
        assert statement_reader.eval_frac(Ratio(0, 1)) == 0.0

    def test_large_values(self):
        assert statement_reader.eval_frac(Ratio(355, 113)) == pytest.approx(
            3.14159, abs=0.001
        )


class TestGpsToDecimal:
    def test_normal(self):
        values = (Ratio(40, 1), Ratio(26, 1), Ratio(46, 1))
        result = statement_reader.gps_to_decimal(values)
        assert result is not None
        assert result == pytest.approx(40.44611, abs=0.001)

    def test_zero(self):
        values = (Ratio(0, 1), Ratio(0, 1), Ratio(0, 1))
        result = statement_reader.gps_to_decimal(values)
        assert result == 0.0

    def test_non_ratio_returns_none(self):
        result = statement_reader.gps_to_decimal((1, 2, 3))
        assert result is None

    def test_zero_denominator_returns_none(self):
        result = statement_reader.gps_to_decimal(
            (Ratio(1, 0), Ratio(0, 1), Ratio(0, 1))
        )
        assert result is None


class TestParseCoordNumeric:
    def test_positive_north(self):
        result = statement_reader._parse_coord_numeric("40.123", "N")
        assert result == pytest.approx(40.123)

    def test_negative_south(self):
        result = statement_reader._parse_coord_numeric("33.5", "S")
        assert result == pytest.approx(-33.5)

    def test_negative_west(self):
        result = statement_reader._parse_coord_numeric("74.0", "W")
        assert result == pytest.approx(-74.0)

    def test_no_ref(self):
        result = statement_reader._parse_coord_numeric("40.0", None)
        assert result == 40.0

    def test_invalid_value(self):
        result = statement_reader._parse_coord_numeric("invalid", "N")
        assert result is None

    def test_invalid_ref(self):
        result = statement_reader._parse_coord_numeric("40.0", "X")
        assert result is None


class TestParseCoordAdobe:
    def test_valid_north(self):
        result = statement_reader._parse_coord_adobe("40,26.46N")
        assert result is not None
        assert result > 0

    def test_valid_south(self):
        result = statement_reader._parse_coord_adobe("33,30.0S")
        assert result is not None
        assert result < 0

    def test_invalid_format(self):
        result = statement_reader._parse_coord_adobe("invalid")
        assert result is None


class TestParseCoord:
    def test_none_coord(self):
        result = statement_reader._parse_coord(None, "N")
        assert result is None

    def test_numeric(self):
        result = statement_reader._parse_coord("40.123", "N")
        assert result == pytest.approx(40.123)

    def test_adobe_fallback(self):
        result = statement_reader._parse_coord("40,26.46N", None)
        assert result is not None


class TestParseIso:
    def test_basic_iso(self):
        result = statement_reader._parse_iso("2023-06-15T10:30:00")
        assert result is not None
        assert result.year == 2023

    def test_iso_with_z(self):
        result = statement_reader._parse_iso("2023-06-15T10:30:00Z")
        assert result is not None
        assert result.tzinfo is not None

    def test_iso_with_offset(self):
        result = statement_reader._parse_iso("2023-06-15T10:30:00+05:30")
        assert result is not None

    def test_invalid(self):
        result = statement_reader._parse_iso("not a date")
        assert result is None


class TestStrptimeAlternativeFormats:
    def test_matches_first_format(self):
        result = statement_reader.strptime_alternative_formats(
            "2023:06:15", ["%Y:%m:%d", "%Y-%m-%d"]
        )
        assert result is not None
        assert result.year == 2023

    def test_matches_second_format(self):
        result = statement_reader.strptime_alternative_formats(
            "2023-06-15", ["%Y:%m:%d", "%Y-%m-%d"]
        )
        assert result is not None

    def test_iso_format(self):
        result = statement_reader.strptime_alternative_formats(
            "2023-06-15T10:30:00", ["ISO"]
        )
        assert result is not None

    def test_no_match(self):
        result = statement_reader.strptime_alternative_formats("invalid", ["%Y:%m:%d"])
        assert result is None


class TestParseTimestrAsTimedelta:
    def test_full_hms(self):
        result = statement_reader.parse_timestr_as_timedelta("10:30:45")
        assert result == datetime.timedelta(hours=10, minutes=30, seconds=45)

    def test_hm_only(self):
        result = statement_reader.parse_timestr_as_timedelta("10:30")
        assert result == datetime.timedelta(hours=10, minutes=30)

    def test_hours_only(self):
        result = statement_reader.parse_timestr_as_timedelta("5")
        assert result == datetime.timedelta(hours=5)

    def test_fractional_seconds(self):
        result = statement_reader.parse_timestr_as_timedelta("10:30:45.5")
        assert result == datetime.timedelta(hours=10, minutes=30, seconds=45.5)

    def test_invalid(self):
        result = statement_reader.parse_timestr_as_timedelta("abc")
        assert result is None

    def test_whitespace_stripped(self):
        result = statement_reader.parse_timestr_as_timedelta("  10:30:45  ")
        assert result == datetime.timedelta(hours=10, minutes=30, seconds=45)


class TestParseTimeRatiosAsTimedelta:
    def test_normal(self):
        time_tuple = [Ratio(10, 1), Ratio(30, 1), Ratio(45, 1)]
        result = statement_reader.parse_time_ratios_as_timedelta(time_tuple)
        assert result == datetime.timedelta(hours=10, minutes=30, seconds=45)

    def test_fractional_seconds(self):
        time_tuple = [Ratio(1, 1), Ratio(2, 1), Ratio(1, 2)]
        result = statement_reader.parse_time_ratios_as_timedelta(time_tuple)
        assert result == datetime.timedelta(hours=1, minutes=2, seconds=0.5)

    def test_invalid_type(self):
        result = statement_reader.parse_time_ratios_as_timedelta([1, 2, 3])
        assert result is None

    def test_zero_denominator(self):
        result = statement_reader.parse_time_ratios_as_timedelta(
            [Ratio(1, 0), Ratio(0, 1), Ratio(0, 1)]
        )
        assert result is None

    def test_too_few_elements(self):
        result = statement_reader.parse_time_ratios_as_timedelta([Ratio(1, 1)])
        assert result is None


class TestParseGpsDatetime:
    def test_iso_format(self):
        result = statement_reader.parse_gps_datetime("2023-06-15T10:30:00Z")
        assert result is not None
        assert result.year == 2023
        assert result.tzinfo is not None

    def test_separate_date_time(self):
        result = statement_reader.parse_gps_datetime("2021:08:02 07:57:06")
        assert result is not None
        assert result.year == 2021
        assert result.hour == 7

    def test_single_value(self):
        result = statement_reader.parse_gps_datetime("2023:06:15")
        assert result is None

    def test_no_tz_gets_default(self):
        result = statement_reader.parse_gps_datetime("2023-06-15T10:30:00")
        assert result is not None
        assert result.tzinfo == datetime.timezone.utc


class TestParseGpsDatetimeSeparately:
    def test_normal(self):
        result = statement_reader.parse_gps_datetime_separately(
            "2021:08:02", "07:57:06"
        )
        assert result is not None
        assert result.year == 2021
        assert result.hour == 7
        assert result.minute == 57

    def test_with_fractional_seconds(self):
        result = statement_reader.parse_gps_datetime_separately(
            "2022:06:10", "17:35:52.269367"
        )
        assert result is not None
        assert result.second == 52

    def test_with_z_suffix(self):
        result = statement_reader.parse_gps_datetime_separately(
            "2022:06:10", "17:35:52.269367Z"
        )
        assert result is not None

    def test_iso_date(self):
        result = statement_reader.parse_gps_datetime_separately(
            "2022-06-10", "17:35:52"
        )
        assert result is not None

    def test_invalid_date(self):
        result = statement_reader.parse_gps_datetime_separately("invalid", "12:00:00")
        assert result is None


class TestParseDatetimestrWithSubsecAndOffset:
    def test_basic(self):
        result = statement_reader.parse_datetimestr_with_subsec_and_offset(
            "2023:06:15 10:30:45", None, None
        )
        assert result is not None
        assert result.year == 2023
        assert result.hour == 10

    def test_with_subsec(self):
        result = statement_reader.parse_datetimestr_with_subsec_and_offset(
            "2023:06:15 10:30:45", "123", None
        )
        assert result is not None
        assert result.microsecond > 0

    def test_with_offset(self):
        result = statement_reader.parse_datetimestr_with_subsec_and_offset(
            "2023:06:15 10:30:45", None, "+05:30"
        )
        assert result is not None
        assert result.tzinfo is not None

    def test_invalid_string(self):
        result = statement_reader.parse_datetimestr_with_subsec_and_offset(
            "invalid", None, None
        )
        assert result is None

    def test_zero_date_returns_none(self):
        result = statement_reader.parse_datetimestr_with_subsec_and_offset(
            "0000:00:00 00:00:00", None, None
        )
        assert result is None
