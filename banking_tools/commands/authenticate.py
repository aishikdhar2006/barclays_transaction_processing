# Copyright (c) Meta Platforms, Inc. and affiliates.
#
# This source code is licensed under the BSD license found in the
# LICENSE file in the root directory of this source tree.

import argparse
import inspect

from ..authenticate import authenticate


class Command:
    name = "authenticate"
    help = "authenticate BankingPlatform users"

    def add_basic_arguments(self, parser: argparse.ArgumentParser):
        parser.add_argument(
            "--user_name",
            help="BankingPlatform user profile",
            default=None,
            required=False,
        )
        parser.add_argument(
            "--user_email",
            help="User email, used to create BankingPlatform account",
            default=None,
            required=False,
        )
        parser.add_argument(
            "--user_password",
            help="Password associated with the BankingPlatform user account",
            default=None,
            required=False,
        )
        parser.add_argument(
            "--jwt",
            help="BankingPlatform user access token",
            default=None,
            required=False,
        )
        parser.add_argument(
            "--delete",
            help="Delete the specified user profile",
            default=False,
            required=False,
            action="store_true",
        )

    def run(self, vars_args: dict):
        authenticate(
            **(
                {
                    k: v
                    for k, v in vars_args.items()
                    if k in inspect.getfullargspec(authenticate).args
                }
            )
        )
