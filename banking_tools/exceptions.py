# Copyright (c) Meta Platforms, Inc. and affiliates.
#
# This source code is licensed under the BSD license found in the
# LICENSE file in the root directory of this source tree.

from __future__ import annotations

import typing as T


class BankingPlatformUserError(Exception):
    exit_code: int


class BankingPlatformProcessError(BankingPlatformUserError):
    """
    Base exception for process specific errors
    """

    exit_code = 6


class BankingPlatformDescriptionError(Exception):
    pass


class BankingPlatformBadParameterError(BankingPlatformUserError):
    exit_code = 2


class BankingPlatformFileNotFoundError(BankingPlatformUserError):
    exit_code = 3


class BankingPlatformInvalidDescriptionFile(BankingPlatformUserError):
    exit_code = 4


class BankingPlatformVideoError(BankingPlatformUserError):
    exit_code = 7


class BankingPlatformFFmpegNotFoundError(BankingPlatformUserError):
    exit_code = 8


class BankingPlatformExiftoolNotFoundError(BankingPlatformUserError):
    exit_code = 8


class BankingPlatformGeoTaggingError(BankingPlatformDescriptionError):
    pass


class BankingPlatformVideoGPSNotFoundError(BankingPlatformDescriptionError):
    pass


class BankingPlatformInvalidVideoError(BankingPlatformDescriptionError):
    pass


class BankingPlatformGPXEmptyError(BankingPlatformDescriptionError):
    pass


class BankingPlatformGPSNoiseError(BankingPlatformDescriptionError):
    pass


class BankingPlatformStationaryVideoError(BankingPlatformDescriptionError):
    pass


class BankingPlatformOutsideGPXTrackError(BankingPlatformDescriptionError):
    def __init__(
        self, message: str, image_time: str, gpx_start_time: str, gpx_end_time: str
    ):
        super().__init__(message)
        self.image_time = image_time
        self.gpx_start_time = gpx_start_time
        self.gpx_end_time = gpx_end_time


class BankingPlatformDuplicationError(BankingPlatformDescriptionError):
    def __init__(
        self,
        message: str,
        desc: T.Mapping[str, T.Any],
        distance: float,
        angle_diff: float | None,
    ) -> None:
        super().__init__(message)
        self.desc = desc
        self.distance = distance
        self.angle_diff = angle_diff


class BankingPlatformExifToolXMLNotFoundError(BankingPlatformDescriptionError):
    pass


class BankingPlatformFileTooLargeError(BankingPlatformDescriptionError):
    pass


class BankingPlatformCaptureSpeedTooFastError(BankingPlatformDescriptionError):
    pass


class BankingPlatformNullIslandError(BankingPlatformDescriptionError):
    pass


class BankingPlatformZigZagError(BankingPlatformDescriptionError):
    pass


class BankingPlatformUploadConnectionError(BankingPlatformUserError):
    exit_code = 12


class BankingPlatformUploadTimeoutError(BankingPlatformUserError):
    exit_code = 13


class BankingPlatformUploadUnauthorizedError(BankingPlatformUserError):
    exit_code = 14


class BankingPlatformMetadataValidationError(BankingPlatformUserError):
    exit_code = 15
