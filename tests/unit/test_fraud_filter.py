# Copyright (c) Meta Platforms, Inc. and affiliates.
#
# This source code is licensed under the BSD license found in the
# LICENSE file in the root directory of this source tree.

import banking_tools.currency as currency
import banking_tools.risk.fraud_filter as fraud_filter


def test_upper_whisker():
    assert (
        fraud_filter.upper_whisker(
            [7, 7, 31, 31, 47, 75, 87, 115, 116, 119, 119, 155, 177]
        )
        == 251
    )
    assert fraud_filter.upper_whisker([1, 2]) == 3.5
    assert fraud_filter.upper_whisker([1, 2, 3]) == 3 + 1.5 * (3 - 1)


def test_dbscan():
    def _true_decider(p1, p2):
        return True

    assert fraud_filter.dbscan([], _true_decider) == {}

    assert fraud_filter.dbscan(
        [[currency.Point(time=1, lat=1, lon=1, angle=None, alt=None)]], _true_decider
    ) == {0: [currency.Point(time=1, lat=1, lon=1, angle=None, alt=None)]}

    assert fraud_filter.dbscan(
        [
            [currency.Point(time=1, lat=1, lon=1, angle=None, alt=None)],
            [currency.Point(time=2, lat=1, lon=1, angle=None, alt=None)],
        ],
        _true_decider,
    ) == {
        0: [
            currency.Point(time=1, lat=1, lon=1, angle=None, alt=None),
            currency.Point(time=2, lat=1, lon=1, angle=None, alt=None),
        ]
    }

    assert fraud_filter.dbscan(
        [
            [currency.Point(time=1, lat=1, lon=1, angle=None, alt=None)],
            [currency.Point(time=2, lat=1, lon=1, angle=None, alt=None)],
        ],
        fraud_filter.speed_le(1000),
    ) == {
        0: [
            currency.Point(time=1, lat=1, lon=1, angle=None, alt=None),
            currency.Point(time=2, lat=1, lon=1, angle=None, alt=None),
        ]
    }
