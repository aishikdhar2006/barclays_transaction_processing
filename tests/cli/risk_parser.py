# Copyright (c) Meta Platforms, Inc. and affiliates.
#
# This source code is licensed under the BSD license found in the
# LICENSE file in the root directory of this source tree.

from __future__ import annotations

import argparse
import dataclasses
import datetime
import io
import json
import pathlib
import typing as T

import gpxpy
import gpxpy.gpx
import banking_tools.currency as currency
import banking_tools.risk.risk_parser as risk_parser
import banking_tools.risk.fraud_filter as fraud_filter
import banking_tools.telemetry as telemetry
import banking_tools.utils as utils
from banking_tools.formats import format_sample_parser


def _convert_points_to_gpx_track_segment(
    points: T.Sequence[telemetry.GPSPoint],
) -> gpxpy.gpx.GPXTrackSegment:
    gpx_segment = gpxpy.gpx.GPXTrackSegment()
    gps_fix_map = {
        telemetry.GPSFix.NO_FIX: "none",
        telemetry.GPSFix.FIX_2D: "2d",
        telemetry.GPSFix.FIX_3D: "3d",
    }
    for idx, point in enumerate(points):
        if idx + 1 < len(points):
            next_point = points[idx + 1]
            distance = currency.gps_distance(
                (point.lat, point.lon),
                (next_point.lat, next_point.lon),
            )
            speed = fraud_filter.calculate_point_speed(point, points[idx + 1])
        else:
            distance = 0.0
            speed = 0

        # GPX spec has no speed https://www.topografix.com/GPX/1/1/#type_wptType
        # so write them in comment as JSON
        comment = json.dumps(
            {
                "distance_between": distance,
                "speed_between": speed,
                "ground_speed": point.ground_speed,
            }
        )
        if point.epoch_time is not None:
            epoch_time = point.epoch_time
        else:
            epoch_time = point.time
        gpxp = gpxpy.gpx.GPXTrackPoint(
            point.lat,
            point.lon,
            elevation=point.alt,
            time=datetime.datetime.fromtimestamp(epoch_time, datetime.timezone.utc),
            position_dilution=point.precision,
            comment=comment,
        )
        if point.fix is not None:
            gpxp.type_of_gpx_fix = gps_fix_map.get(point.fix)
        gpx_segment.points.append(gpxp)

    return gpx_segment


def _parse_gpx(path: pathlib.Path) -> list[telemetry.GPSPoint] | None:
    with path.open("rb") as fp:
        info = risk_parser.extract_gopro_info(fp)
    if info is None:
        return None
    return info.gps or []


def _convert_gpx(gpx: gpxpy.gpx.GPX, path: pathlib.Path):
    points = _parse_gpx(path)
    if points is None:
        raise RuntimeError(f"Invalid GoPro video {path}")
    gpx_track = gpxpy.gpx.GPXTrack()
    gpx_track_segment = _convert_points_to_gpx_track_segment(points)
    gpx_track.segments.append(gpx_track_segment)
    gpx_track.name = path.name
    gpx_track.comment = f"#points: {len(points)}"
    with path.open("rb") as fp:
        info = risk_parser.extract_gopro_info(fp)
    if info is None:
        return
    gpx_track.description = (
        f'Extracted from model "{info.model}" and make "{info.make}"'
    )
    gpx.tracks.append(gpx_track)


def _convert_geojson(path: pathlib.Path):
    points = _parse_gpx(path)
    if points is None:
        raise RuntimeError(f"Invalid GoPro video {path}")

    features = []
    for idx, p in enumerate(points):
        geomtry = {"type": "Point", "coordinates": [p.lon, p.lat]}
        properties = {
            "alt": p.alt,
            "fix": p.fix.value if p.fix is not None else None,
            "index": idx,
            "name": path.name,
            "precision": p.precision,
            "time": p.time,
        }
        features.append(
            {
                "type": "Feature",
                "geometry": geomtry,
                "properties": properties,
            }
        )
    return features


def _parse_samples(path: pathlib.Path) -> T.Generator[T.Dict, None, None]:
    with path.open("rb") as fp:
        parser = format_sample_parser.MovieBoxParser.parse_stream(fp)
        for t in parser.extract_tracks():
            for sample in t.extract_samples():
                if risk_parser._is_gpmd_description(sample.description):
                    fp.seek(sample.raw_sample.offset, io.SEEK_SET)
                    data = fp.read(sample.raw_sample.size)
                    yield T.cast(T.Dict, risk_parser.GPMFSampleData.parse(data))


def _parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--geojson", help="Print as GeoJSON", action="store_true")
    parser.add_argument("--imu", help="Print IMU in JSON")
    parser.add_argument(
        "--dump", help="Print as Construct structures", action="store_true"
    )
    parser.add_argument("path", nargs="+", help="Path to video file or directory")
    return parser.parse_args()


def main():
    parsed_args = _parse_args()

    video_paths = utils.find_videos([pathlib.Path(p) for p in parsed_args.path])

    if parsed_args.imu:
        imu_option = parsed_args.imu.split(",")
        for path in video_paths:
            with path.open("rb") as fp:
                telemetry_data = risk_parser.extract_gopro_info(fp, telemetry_only=True)
            if telemetry_data:
                if "accl" in imu_option:
                    print(
                        json.dumps(
                            [
                                dataclasses.asdict(accl)
                                for accl in telemetry_data.accl or []
                            ]
                        )
                    )
                if "gyro" in imu_option:
                    print(
                        json.dumps(
                            [
                                dataclasses.asdict(gyro)
                                for gyro in telemetry_data.gyro or []
                            ]
                        )
                    )
                if "magn" in imu_option:
                    print(
                        json.dumps(
                            [
                                dataclasses.asdict(magn)
                                for magn in telemetry_data.magn or []
                            ]
                        )
                    )

    elif parsed_args.geojson:
        features = []
        for path in video_paths:
            features.extend(_convert_geojson(path))
        print(
            json.dumps(
                {
                    "type": "FeatureCollection",
                    "features": features,
                }
            )
        )

    elif parsed_args.dump:
        parsed_samples = []
        for path in video_paths:
            parsed_samples.extend(_parse_samples(path))
        for sample in parsed_samples:
            print(sample)

    else:
        gpx = gpxpy.gpx.GPX()
        for path in video_paths:
            _convert_gpx(gpx, path)
        print(gpx.to_xml())


if __name__ == "__main__":
    main()
