# Copyright (c) Meta Platforms, Inc. and affiliates.
#
# This source code is licensed under the BSD license found in the
# LICENSE file in the root directory of this source tree.

import datetime
from unittest.mock import MagicMock


from banking_tools.risk import risk_parser


class TestExtractCameraModelFromDevices:
    def test_empty_devices(self):
        assert risk_parser._extract_camera_model_from_devices({}) == ""

    def test_single_hero(self):
        result = risk_parser._extract_camera_model_from_devices({0: b"Hero11 Black"})
        assert result == "Hero11 Black"

    def test_hero_priority(self):
        result = risk_parser._extract_camera_model_from_devices(
            {0: b"Some Camera", 1: b"Hero11 Black"}
        )
        assert result == "Hero11 Black"

    def test_gopro_priority(self):
        result = risk_parser._extract_camera_model_from_devices(
            {0: b"Some Camera", 1: b"GoPro Max"}
        )
        assert result == "GoPro Max"

    def test_fallback_to_first(self):
        result = risk_parser._extract_camera_model_from_devices(
            {0: b"Camera A", 1: b"Camera B"}
        )
        assert result == "Camera A"

    def test_unicode_decode_error(self):
        result = risk_parser._extract_camera_model_from_devices({0: b"\xff\xfe"})
        assert result == ""

    def test_strips_whitespace(self):
        result = risk_parser._extract_camera_model_from_devices(
            {0: b"  Hero11 Black  "}
        )
        assert result == "Hero11 Black"


class TestGps5TimestampToEpochTime:
    def test_valid_timestamp(self):
        result = risk_parser._gps5_timestamp_to_epoch_time("230615120000.000")
        dt = datetime.datetime.fromtimestamp(result, tz=datetime.timezone.utc)
        assert dt.year == 2023
        assert dt.month == 6
        assert dt.day == 15
        assert dt.hour == 12


class TestIsGpmdDescription:
    def test_gpmd(self):
        assert risk_parser._is_gpmd_description({"format": b"gpmd"}) is True

    def test_not_gpmd(self):
        assert risk_parser._is_gpmd_description({"format": b"avc1"}) is False


class TestGoProInfo:
    def test_default_values(self):
        info = risk_parser.GoProInfo()
        assert info.gps is None
        assert info.make == "GoPro"
        assert info.model == ""
        assert info.accl is None
        assert info.gyro is None
        assert info.magn is None


class TestKLVDict:
    def test_type_dict(self):
        klv: risk_parser.KLVDict = {
            "key": b"GPS5",
            "type": b"l",
            "structure_size": 20,
            "repeat": 1,
            "data": [[0, 0, 0, 0, 0]],
        }
        assert klv["key"] == b"GPS5"


def _gps_point(time, epoch_time=None):
    from banking_tools import telemetry

    return telemetry.GPSPoint(
        time=time,
        lat=0.0,
        lon=0.0,
        alt=None,
        angle=None,
        epoch_time=epoch_time,
        fix=None,
        precision=None,
        ground_speed=None,
    )


class TestFindFirstDeviceId:
    def test_found(self):
        stream = [{"key": b"DVID", "data": [[42]]}]
        assert risk_parser._find_first_device_id(stream) == 42

    def test_not_found_default(self):
        stream = [{"key": b"DVNM", "data": [b"x"]}]
        assert risk_parser._find_first_device_id(stream) == 2**32


class TestFindFirstGpsStream:
    def test_no_strm(self):
        assert (
            risk_parser._find_first_gps_stream([{"key": b"DVID", "data": [[1]]}]) == []
        )


class TestIsMatrixCalibration:
    def test_orientation_only(self):
        assert risk_parser._is_matrix_calibration([1, 0, 0, 0, -1, 0, 0, 0, 1]) is False

    def test_real_calibration(self):
        assert risk_parser._is_matrix_calibration([0.5, 0, 0, 0, 1, 0, 0, 0, 1]) is True


class TestBuildMatrix:
    def test_identity(self):
        matrix = risk_parser._build_matrix(b"xyz", b"xyz")
        assert matrix == [1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0]

    def test_inversion(self):
        # uppercase X is inverse of lowercase x
        matrix = risk_parser._build_matrix(b"X", b"x")
        assert matrix == [-1.0]


class TestApplyMatrix:
    def test_identity_matrix(self):
        result = list(risk_parser._apply_matrix([1, 0, 0, 1], [3, 4]))
        assert result == [3, 4]

    def test_swap_matrix(self):
        result = list(risk_parser._apply_matrix([0, 1, 1, 0], [3, 4]))
        assert result == [4, 3]


class TestFlatten:
    def test_flatten(self):
        assert risk_parser._flatten([[1, 2], [3, 4]]) == [1, 2, 3, 4]

    def test_empty(self):
        assert risk_parser._flatten([]) == []


class TestGetMatrix:
    def test_mtrx_calibration(self):
        klv = {b"MTRX": {"key": b"MTRX", "data": [[0.5, 0, 0, 0, 1, 0, 0, 0, 1]]}}
        result = risk_parser._get_matrix(klv)
        assert result == [0.5, 0, 0, 0, 1, 0, 0, 0, 1]

    def test_mtrx_non_calibration_ignored(self):
        klv = {b"MTRX": {"key": b"MTRX", "data": [[1, 0, 0, 0, 1, 0, 0, 0, 1]]}}
        assert risk_parser._get_matrix(klv) is None

    def test_orin_orio(self):
        klv = {
            b"ORIN": {"key": b"ORIN", "data": [b"xyz"]},
            b"ORIO": {"key": b"ORIO", "data": [b"xyz"]},
        }
        result = risk_parser._get_matrix(klv)
        assert result == [1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0]

    def test_none(self):
        assert risk_parser._get_matrix({}) is None


class TestScaleAndCalibrate:
    def test_basic_scaling(self):
        stream = [
            {"key": b"ACCL", "data": [[10.0, 20.0, 30.0]]},
            {"key": b"SCAL", "data": [[10]]},
        ]
        result = list(risk_parser._scale_and_calibrate(stream, b"ACCL"))
        assert result == [(1.0, 2.0, 3.0)]

    def test_missing_key_returns_empty(self):
        stream = [{"key": b"SCAL", "data": [[10]]}]
        assert list(risk_parser._scale_and_calibrate(stream, b"ACCL")) == []

    def test_multiple_scals(self):
        stream = [
            {"key": b"GYRO", "data": [[10.0, 40.0]]},
            {"key": b"SCAL", "data": [[10], [4]]},
        ]
        result = list(risk_parser._scale_and_calibrate(stream, b"GYRO"))
        assert result == [(1.0, 10.0)]


class TestFindFirstTelemetryStream:
    def test_found(self):
        stream = [
            {
                "key": b"STRM",
                "data": [
                    {"key": b"ACCL", "data": [[10.0, 20.0, 30.0]]},
                    {"key": b"SCAL", "data": [[10]]},
                ],
            }
        ]
        result = risk_parser._find_first_telemetry_stream(stream, b"ACCL")
        assert result == [(1.0, 2.0, 3.0)]

    def test_not_found(self):
        assert risk_parser._find_first_telemetry_stream([], b"ACCL") == []


class TestAccumulateXyzTelemetry:
    def test_accumulates(self):
        from banking_tools import telemetry

        sample = MagicMock()
        sample.exact_time = 100.0
        sample.exact_timedelta = 1.0
        device_data = [
            {
                "key": b"STRM",
                "data": [
                    {"key": b"ACCL", "data": [[1.0, 2.0, 3.0]]},
                    {"key": b"SCAL", "data": [[1]]},
                ],
            }
        ]
        output: dict = {}
        risk_parser._accumulate_xyz_telemetry(
            device_data, sample, b"ACCL", telemetry.AccelerationData, output, 7
        )
        assert 7 in output
        assert len(output[7]) == 1

    def test_no_samples_no_output(self):
        from banking_tools import telemetry

        sample = MagicMock()
        sample.exact_time = 0.0
        sample.exact_timedelta = 1.0
        output: dict = {}
        risk_parser._accumulate_xyz_telemetry(
            [], sample, b"ACCL", telemetry.AccelerationData, output, 1
        )
        assert output == {}


class TestBackfillGpsTimestamps:
    def test_backfill_forward(self):
        points = [
            _gps_point(0.0, epoch_time=None),
            _gps_point(1.0, epoch_time=1000.0),
            _gps_point(2.0, epoch_time=None),
        ]
        risk_parser._backfill_gps_timestamps(points)
        assert points[2].epoch_time == 1001.0

    def test_no_epoch_returns_early(self):
        points = [_gps_point(0.0), _gps_point(1.0)]
        risk_parser._backfill_gps_timestamps(points)
        assert all(p.epoch_time is None for p in points)
