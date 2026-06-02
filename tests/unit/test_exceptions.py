# Copyright (c) Meta Platforms, Inc. and affiliates.
#
# This source code is licensed under the BSD license found in the
# LICENSE file in the root directory of this source tree.

import json
from pathlib import Path

from banking_tools import exceptions, types
from banking_tools.serializer import description


def test_all():
    all_excs = [
        getattr(exceptions, ex)
        for ex in dir(exceptions)
        if ex.startswith("BankingPlatform") and ex.endswith("Error")
    ]

    all_desc_excs = [
        exc
        for exc in all_excs
        if issubclass(exc, exceptions.BankingPlatformDescriptionError)
    ]

    for exc in all_desc_excs:
        if exc is exceptions.BankingPlatformOutsideGPXTrackError:
            e = exc("hello", "world", "hey", "aa")
        elif exc is exceptions.BankingPlatformDuplicationError:
            e = exc("hello", {}, 1, float("inf"))
        else:
            e = exc("hello")
        # should not raise
        json.dumps(
            description.DescriptionJSONSerializer._as_error_desc(
                e, Path("test.jpg"), types.FileType.IMAGE
            )
        )
