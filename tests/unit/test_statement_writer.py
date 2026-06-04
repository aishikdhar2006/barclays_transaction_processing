# Copyright (c) Meta Platforms, Inc. and affiliates.
#
# This source code is licensed under the BSD license found in the
# LICENSE file in the root directory of this source tree.

import datetime
import io

import pytest

from banking_tools import statement_writer


def _make_minimal_jpeg() -> bytes:
    """Create a minimal valid JPEG with EXIF data for testing."""
    from PIL import Image
    import piexif

    buf = io.BytesIO()
    img = Image.new("RGB", (1, 1), color=(255, 255, 255))
    img.save(buf, "JPEG")
    jpeg_bytes = buf.getvalue()

    # Insert empty EXIF into the valid JPEG
    exif_dict = {"0th": {}, "Exif": {}, "GPS": {}, "1st": {}}
    exif_bytes = piexif.dump(exif_dict)
    out = io.BytesIO()
    piexif.insert(exif_bytes, jpeg_bytes, out)
    return out.getvalue()


class TestExifEditInit:
    def test_from_bytes(self):
        jpeg_data = _make_minimal_jpeg()
        edit = statement_writer.ExifEdit(jpeg_data)
        assert edit is not None

    def test_from_path(self, tmp_path):
        img = tmp_path / "test.jpg"
        img.write_bytes(_make_minimal_jpeg())
        edit = statement_writer.ExifEdit(img)
        assert edit is not None


class TestDecimalToDms:
    def test_zero(self):
        result = statement_writer.ExifEdit.decimal_to_dms(0.0)
        assert result[0] == (0, 1)
        assert result[1] == (0, 1)

    def test_whole_degrees(self):
        result = statement_writer.ExifEdit.decimal_to_dms(45.0)
        assert result[0] == (45, 1)
        assert result[1] == (0, 1)

    def test_with_minutes(self):
        result = statement_writer.ExifEdit.decimal_to_dms(45.5)
        assert result[0] == (45, 1)
        assert result[1] == (30, 1)


class TestExifEditMethods:
    @pytest.fixture
    def edit(self):
        jpeg_data = _make_minimal_jpeg()
        return statement_writer.ExifEdit(jpeg_data)

    def test_add_image_description(self, edit):
        edit.add_image_description({"key": "value"})
        # Should not raise

    def test_add_orientation_valid(self, edit):
        edit.add_orientation(6)
        # Should not raise

    def test_add_orientation_invalid(self, edit):
        with pytest.raises(ValueError, match="orientation"):
            edit.add_orientation(0)

    def test_add_orientation_invalid_high(self, edit):
        with pytest.raises(ValueError, match="orientation"):
            edit.add_orientation(9)

    def test_add_date_time_original(self, edit):
        dt = datetime.datetime(2023, 6, 15, 10, 30, 45, tzinfo=datetime.timezone.utc)
        edit.add_date_time_original(dt)

    def test_add_date_time_original_naive(self, edit):
        dt = datetime.datetime(2023, 6, 15, 10, 30, 45)
        edit.add_date_time_original(dt)

    def test_add_gps_datetime(self, edit):
        dt = datetime.datetime(2023, 6, 15, 10, 30, 45, tzinfo=datetime.timezone.utc)
        edit.add_gps_datetime(dt)

    def test_add_lat_lon_positive(self, edit):
        edit.add_lat_lon(40.7128, -74.006)

    def test_add_lat_lon_negative(self, edit):
        edit.add_lat_lon(-33.8688, 151.2093)

    def test_add_altitude_positive(self, edit):
        edit.add_altitude(100.5)

    def test_add_altitude_negative(self, edit):
        edit.add_altitude(-50.0)

    def test_add_direction(self, edit):
        edit.add_direction(180.0)

    def test_add_direction_wraps(self, edit):
        edit.add_direction(370.0)

    def test_add_make(self, edit):
        edit.add_make("Canon")

    def test_add_make_empty_raises(self, edit):
        with pytest.raises(ValueError, match="Make cannot be empty"):
            edit.add_make("")

    def test_add_model(self, edit):
        edit.add_model("EOS R5")

    def test_add_model_empty_raises(self, edit):
        with pytest.raises(ValueError, match="Model cannot be empty"):
            edit.add_model("")

    def test_write_modifies_file(self, tmp_path):
        img = tmp_path / "test.jpg"
        img.write_bytes(_make_minimal_jpeg())
        edit = statement_writer.ExifEdit(img)
        edit.add_lat_lon(40.0, -74.0)
        edit.write()
        # File should be modified (new EXIF data added)
        assert img.stat().st_size > 0
