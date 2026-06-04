# Copyright (c) Meta Platforms, Inc. and affiliates.
#
# This source code is licensed under the BSD license found in the
# LICENSE file in the root directory of this source tree.

import datetime
from unittest.mock import MagicMock, patch

import pytest

from banking_tools import swift_parser


class TestExtractCameraModelFromCprt:
    def test_json_format(self):
        cprt = b' {"model":"DR900X Plus","ver":0.918}'
        assert swift_parser._extract_camera_model_from_cprt(cprt) == "DR900X Plus"

    def test_semicolon_format(self):
        cprt = b" Pittasoft Co., Ltd.;DR900S-1CH;1.008;English;"
        assert swift_parser._extract_camera_model_from_cprt(cprt) == "DR900S-1CH"

    def test_empty_model_in_json(self):
        cprt = b' {"model":"","ver":0.918}'
        assert swift_parser._extract_camera_model_from_cprt(cprt) == ""

    def test_no_model_in_json(self):
        cprt = b' {"ver":0.918}'
        assert swift_parser._extract_camera_model_from_cprt(cprt) == ""

    def test_unicode_decode_error(self):
        cprt = b"\xff\xfe"
        assert swift_parser._extract_camera_model_from_cprt(cprt) == ""

    def test_single_field_semicolons(self):
        cprt = b" Company"
        assert swift_parser._extract_camera_model_from_cprt(cprt) == ""


class TestBlackVueInfo:
    def test_defaults(self):
        info = swift_parser.BlackVueInfo()
        assert info.gps is None
        assert info.make == "BlackVue"
        assert info.model == ""


class TestComputeTimezoneOffsetFromRmc:
    def test_valid_rmc(self):
        msg = MagicMock()
        msg.sentence_type = "RMC"
        msg.datetime = datetime.datetime(
            2023, 6, 15, 12, 0, 0, tzinfo=datetime.timezone.utc
        )
        epoch_sec = datetime.datetime(
            2023, 6, 15, 12, 0, 0, tzinfo=datetime.timezone.utc
        ).timestamp()
        result = swift_parser._compute_timezone_offset_from_rmc(epoch_sec, msg)
        assert result == 0.0

    def test_non_rmc_returns_none(self):
        msg = MagicMock()
        msg.sentence_type = "GGA"
        result = swift_parser._compute_timezone_offset_from_rmc(0, msg)
        assert result is None

    def test_no_datetime_returns_none(self):
        msg = MagicMock(spec=[])
        msg.sentence_type = "RMC"
        result = swift_parser._compute_timezone_offset_from_rmc(0, msg)
        assert result is None


class TestComputeTimezoneOffsetFromTimeOnly:
    def test_same_time(self):
        msg = MagicMock()
        msg.timestamp = datetime.time(12, 0, 0)
        epoch = datetime.datetime(
            2023, 6, 15, 12, 0, 0, tzinfo=datetime.timezone.utc
        ).timestamp()
        result = swift_parser._compute_timezone_offset_from_time_only(epoch, msg)
        assert result == 0.0

    def test_no_timestamp_returns_none(self):
        msg = MagicMock(spec=[])
        result = swift_parser._compute_timezone_offset_from_time_only(0, msg)
        assert result is None


class TestParseNmeaLines:
    def test_valid_nmea(self):
        # GGA sentence with valid checksum
        gps_data = b"[1000] $GPGGA,123519,4807.038,N,01131.000,E,1,08,0.9,545.4,M,47.0,M,,*4F\n"
        results = list(swift_parser._parse_nmea_lines(gps_data))
        assert len(results) == 1
        epoch_ms, msg = results[0]
        assert epoch_ms == 1000

    def test_invalid_line_skipped(self):
        gps_data = b"invalid line\n"
        results = list(swift_parser._parse_nmea_lines(gps_data))
        assert results == []

    def test_empty_data(self):
        results = list(swift_parser._parse_nmea_lines(b""))
        assert results == []


class TestDetectTimezoneOffset:
    def test_empty_list(self):
        result = swift_parser._detect_timezone_offset([])
        assert result == 0.0

    def test_rmc_used_first(self):
        gps_data = b"[1484007031000]$GNRMC,001031.00,A,4404.13993,N,12118.86023,W,0.146,,100117,,,A*7B"
        parsed = list(swift_parser._parse_nmea_lines(gps_data))
        parsed_secs = [(round(ms / 1000, 3), msg) for ms, msg in parsed]
        offset = swift_parser._detect_timezone_offset(parsed_secs)
        assert isinstance(offset, float)

    def test_gga_fallback(self):
        gps_data = b"[1623097530000]$GPGGA,202530.00,5109.0262,N,11401.8407,W,5,40,0.5,1097.36,M,-17.00,M,18,TSTR*61"
        parsed = list(swift_parser._parse_nmea_lines(gps_data))
        parsed_secs = [(round(ms / 1000, 3), msg) for ms, msg in parsed]
        offset = swift_parser._detect_timezone_offset(parsed_secs)
        assert isinstance(offset, float)


class TestParseGpsBox:
    def test_gga_point(self):
        data = b"[1623057074211]$GPGGA,202530.00,5109.0262,N,11401.8407,W,5,40,0.5,1097.36,M,-17.00,M,18,TSTR*61"
        points = swift_parser._parse_gps_box(data)
        assert len(points) == 1
        assert points[0].lat == pytest.approx(51.150436, abs=1e-4)
        assert points[0].lon == pytest.approx(-114.030678, abs=1e-4)
        assert points[0].alt == pytest.approx(1097.36, abs=1e-2)

    def test_gll_point(self):
        data = b"[1629874404069]$GNGLL,4404.14012,N,12118.85993,W,001037.00,A,A*67"
        points = swift_parser._parse_gps_box(data)
        assert len(points) == 1
        assert points[0].alt is None

    def test_rmc_point(self):
        data = b"[1629874404069]$GNRMC,001031.00,A,4404.13993,N,12118.86023,W,0.146,,100117,,,A*7B"
        points = swift_parser._parse_gps_box(data)
        assert len(points) == 1

    def test_vtg_only_returns_empty(self):
        data = b"[1623057074211]$GPVTG,,T,,M,0.078,N,0.144,K,D*28"
        points = swift_parser._parse_gps_box(data)
        assert points == []

    def test_empty_data(self):
        assert swift_parser._parse_gps_box(b"") == []


class TestExtractBlackvueInfo:
    def test_no_gps_data_returns_none(self):
        from banking_tools.formats import simple_format_parser as sparser

        fp = MagicMock()
        with patch.object(
            sparser, "parse_mp4_data_first", side_effect=sparser.ParsingError("x")
        ):
            assert swift_parser.extract_blackvue_info(fp) is None

    def test_gps_data_none_returns_none(self):
        from banking_tools.formats import simple_format_parser as sparser

        fp = MagicMock()
        with patch.object(sparser, "parse_mp4_data_first", return_value=None):
            assert swift_parser.extract_blackvue_info(fp) is None

    def test_with_gps_and_model(self):
        from banking_tools.formats import simple_format_parser as sparser

        gps_box = b"[1623057074211]$GPGGA,202530.00,5109.0262,N,11401.8407,W,5,40,0.5,1097.36,M,-17.00,M,18,TSTR*61"
        cprt = b' {"model":"DR900X Plus","ver":0.918}'

        def fake_parse(fp, path):
            if path == [b"free", b"gps "]:
                return gps_box
            if path == [b"free", b"cprt"]:
                return cprt
            return None

        fp = MagicMock()
        with patch.object(sparser, "parse_mp4_data_first", side_effect=fake_parse):
            info = swift_parser.extract_blackvue_info(fp)
        assert info is not None
        assert info.model == "DR900X Plus"
        assert info.gps and len(info.gps) == 1
        # first point time should be relative (0.0)
        assert info.gps[0].time == 0.0

    def test_with_gps_no_cprt(self):
        from banking_tools.formats import simple_format_parser as sparser

        gps_box = b"[1623057074211]$GPGGA,202530.00,5109.0262,N,11401.8407,W,5,40,0.5,1097.36,M,-17.00,M,18,TSTR*61"

        def fake_parse(fp, path):
            if path == [b"free", b"gps "]:
                return gps_box
            raise sparser.ParsingError("no cprt")

        fp = MagicMock()
        with patch.object(sparser, "parse_mp4_data_first", side_effect=fake_parse):
            info = swift_parser.extract_blackvue_info(fp)
        assert info is not None
        assert info.model == ""
