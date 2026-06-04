# Copyright (c) Meta Platforms, Inc. and affiliates.
#
# This source code is licensed under the BSD license found in the
# LICENSE file in the root directory of this source tree.

from pathlib import Path

import pytest

from banking_tools import statement_reader


def _make_jpeg_with_exif(tmp_path) -> Path:
    """Create a minimal JPEG with basic EXIF data."""
    from PIL import Image
    import piexif

    img = Image.new("RGB", (10, 10))
    exif_dict = {
        "0th": {
            piexif.ImageIFD.Make: b"TestMake",
            piexif.ImageIFD.Model: b"TestModel",
            piexif.ImageIFD.Orientation: 1,
        },
        "Exif": {
            piexif.ExifIFD.PixelXDimension: 10,
            piexif.ExifIFD.PixelYDimension: 10,
            piexif.ExifIFD.DateTimeOriginal: b"2023:06:15 10:30:45",
        },
        "GPS": {
            piexif.GPSIFD.GPSLatitudeRef: b"N",
            piexif.GPSIFD.GPSLatitude: ((40, 1), (42, 1), (46, 1)),
            piexif.GPSIFD.GPSLongitudeRef: b"W",
            piexif.GPSIFD.GPSLongitude: ((74, 1), (0, 1), (22, 1)),
            piexif.GPSIFD.GPSAltitudeRef: 0,
            piexif.GPSIFD.GPSAltitude: (100, 1),
            piexif.GPSIFD.GPSImgDirection: (180, 1),
            piexif.GPSIFD.GPSImgDirectionRef: b"T",
        },
        "1st": {},
    }
    exif_bytes = piexif.dump(exif_dict)
    path = tmp_path / "test.jpg"
    img.save(str(path), exif=exif_bytes)
    return path


class TestExifReadFromEXIF:
    def test_extract_make(self, tmp_path):
        path = _make_jpeg_with_exif(tmp_path)
        reader = statement_reader.ExifReadFromEXIF(path)
        result = reader.extract_make()
        assert result is not None
        assert "TestMake" in result

    def test_extract_model(self, tmp_path):
        path = _make_jpeg_with_exif(tmp_path)
        reader = statement_reader.ExifReadFromEXIF(path)
        result = reader.extract_model()
        assert result is not None
        assert "TestModel" in result

    def test_extract_width(self, tmp_path):
        path = _make_jpeg_with_exif(tmp_path)
        reader = statement_reader.ExifReadFromEXIF(path)
        result = reader.extract_width()
        assert result == 10

    def test_extract_height(self, tmp_path):
        path = _make_jpeg_with_exif(tmp_path)
        reader = statement_reader.ExifReadFromEXIF(path)
        result = reader.extract_height()
        assert result == 10

    def test_extract_orientation(self, tmp_path):
        path = _make_jpeg_with_exif(tmp_path)
        reader = statement_reader.ExifReadFromEXIF(path)
        result = reader.extract_orientation()
        assert result == 1

    def test_extract_altitude(self, tmp_path):
        path = _make_jpeg_with_exif(tmp_path)
        reader = statement_reader.ExifReadFromEXIF(path)
        result = reader.extract_altitude()
        assert result == pytest.approx(100.0)

    def test_extract_direction(self, tmp_path):
        path = _make_jpeg_with_exif(tmp_path)
        reader = statement_reader.ExifReadFromEXIF(path)
        result = reader.extract_direction()
        assert result == pytest.approx(180.0)

    def test_extract_lon_lat(self, tmp_path):
        path = _make_jpeg_with_exif(tmp_path)
        reader = statement_reader.ExifReadFromEXIF(path)
        result = reader.extract_lon_lat()
        assert result is not None
        lon, lat = result
        assert lat == pytest.approx(40.7128, abs=0.01)
        assert lon == pytest.approx(-74.006, abs=0.01)

    def test_extract_capture_time(self, tmp_path):
        path = _make_jpeg_with_exif(tmp_path)
        reader = statement_reader.ExifReadFromEXIF(path)
        result = reader.extract_capture_time()
        assert result is not None
        assert result.year == 2023

    def test_from_stream(self, tmp_path):
        path = _make_jpeg_with_exif(tmp_path)
        with path.open("rb") as fp:
            reader = statement_reader.ExifReadFromEXIF(fp)
            result = reader.extract_make()
            assert result is not None

    def test_empty_image(self, tmp_path):
        from PIL import Image

        img = Image.new("RGB", (1, 1))
        path = tmp_path / "noexif.jpg"
        img.save(str(path))
        reader = statement_reader.ExifReadFromEXIF(path)
        result = reader.extract_make()
        assert result is None


class TestExifRead:
    def test_xmp_fallback(self, tmp_path):
        from PIL import Image

        # Image with no EXIF but with XMP in ApplicationNotes
        img = Image.new("RGB", (1, 1))
        path = tmp_path / "test.jpg"
        img.save(str(path))
        reader = statement_reader.ExifRead(path)
        # Should return None without crashing when no XMP/EXIF
        assert reader.extract_altitude() is None
        assert reader.extract_direction() is None
        assert reader.extract_lon_lat() is None
        assert reader.extract_capture_time() is None

    def test_with_exif_data(self, tmp_path):
        path = _make_jpeg_with_exif(tmp_path)
        reader = statement_reader.ExifRead(path)
        assert reader.extract_altitude() == pytest.approx(100.0)
        assert reader.extract_direction() == pytest.approx(180.0)
        assert reader.extract_capture_time() is not None
        assert reader.extract_lon_lat() is not None


class TestExifReadFromEXIFApplicationNotes:
    def test_extract_application_notes_none(self, tmp_path):
        from PIL import Image

        img = Image.new("RGB", (1, 1))
        path = tmp_path / "test.jpg"
        img.save(str(path))
        reader = statement_reader.ExifReadFromEXIF(path)
        result = reader.extract_application_notes()
        assert result is None


def _make_xmp_etree(attrs: dict) -> "object":
    """Build an ElementTree mimicking an XMP rdf:Description with the given
    prefixed attributes (e.g. {"exif:GPSAltitude": "100.5"})."""
    import xml.etree.ElementTree as et

    ns_decls = " ".join(
        f'xmlns:{prefix}="{uri}"'
        for prefix, uri in statement_reader.XMP_NAMESPACES.items()
    )
    attr_str = " ".join(f'{k}="{v}"' for k, v in attrs.items())
    xml = (
        f"<x:xmpmeta {ns_decls}>"
        f"<rdf:RDF><rdf:Description {attr_str}/></rdf:RDF>"
        f"</x:xmpmeta>"
    )
    root = et.fromstring(xml)
    return et.ElementTree(root)


class TestExifReadXMPFallback:
    """Exercise the EXIF->XMP fallback paths in ExifRead by providing an image
    without EXIF and stubbing the XMP reader."""

    def _reader_with_xmp(self, tmp_path, xmp_attrs):
        from PIL import Image

        img = Image.new("RGB", (1, 1))
        path = tmp_path / "noexif.jpg"
        img.save(str(path))
        reader = statement_reader.ExifRead(path)
        xmp_reader = statement_reader.ExifReadFromXMP(_make_xmp_etree(xmp_attrs))
        reader._cached_xml = xmp_reader
        reader._xml_extracted = True
        return reader

    def test_altitude_fallback(self, tmp_path):
        reader = self._reader_with_xmp(tmp_path, {"exif:GPSAltitude": "55.5"})
        assert reader.extract_altitude() == pytest.approx(55.5)

    def test_capture_time_fallback(self, tmp_path):
        reader = self._reader_with_xmp(
            tmp_path, {"exif:DateTimeOriginal": "2017:01:01 01:01:01"}
        )
        dt = reader.extract_capture_time()
        assert dt is not None and dt.year == 2017

    def test_lon_lat_fallback(self, tmp_path):
        reader = self._reader_with_xmp(
            tmp_path,
            {
                "exif:GPSLatitude": "10.0",
                "exif:GPSLatitudeRef": "N",
                "exif:GPSLongitude": "20.0",
                "exif:GPSLongitudeRef": "E",
            },
        )
        result = reader.extract_lon_lat()
        assert result == (pytest.approx(20.0), pytest.approx(10.0))

    def test_make_model_fallback(self, tmp_path):
        reader = self._reader_with_xmp(
            tmp_path, {"tiff:Make": "XmpMake", "tiff:Model": "XmpModel"}
        )
        assert reader.extract_make() == "XmpMake"
        assert reader.extract_model() == "XmpModel"

    def test_fallback_returns_none_when_xmp_empty(self, tmp_path):
        reader = self._reader_with_xmp(tmp_path, {})
        assert reader.extract_altitude() is None
        assert reader.extract_make() is None
        assert reader.extract_model() is None
        assert reader.extract_lon_lat() is None
        assert reader.extract_capture_time() is None

    def test_fallback_returns_none_when_no_xmp(self, tmp_path):
        from PIL import Image

        img = Image.new("RGB", (1, 1))
        path = tmp_path / "noexif.jpg"
        img.save(str(path))
        reader = statement_reader.ExifRead(path)
        reader._cached_xml = None
        reader._xml_extracted = True
        assert reader.extract_altitude() is None
        assert reader.extract_make() is None
        assert reader.extract_model() is None
        assert reader.extract_lon_lat() is None
        assert reader.extract_capture_time() is None
