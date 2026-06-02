# Copyright (c) Meta Platforms, Inc. and affiliates.
#
# This source code is licensed under the BSD license found in the
# LICENSE file in the root directory of this source tree.

import argparse
from pathlib import Path

from banking_tools.ledger import ledger_builder
from banking_tools.compliance import validate_batches_from_batch
from banking_tools.formats import simple_format_builder as builder
from banking_tools.processor import VideoUploader


def _parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("source_mp4_path", help="where to read the MP4")
    parser.add_argument("target_mp4_path", help="where to write the transformed MP4")
    return parser.parse_args()


def main():
    parsed_args = _parse_args()
    video_metadatas = validate_batches_from_batch.GeotagVideosFromVideo().to_description(
        [Path(parsed_args.source_mp4_path)]
    )
    generator = ledger_builder.ledger_sample_generator2(
        VideoUploader.prepare_camm_info(video_metadatas[0])
    )
    with open(parsed_args.source_mp4_path, "rb") as src_fp:
        with open(parsed_args.target_mp4_path, "wb") as tar_fp:
            reader = builder.transform_mp4(
                src_fp,
                generator,
            )
            while True:
                data = reader.read(1024 * 1024 * 64)
                if not data:
                    break
                tar_fp.write(data)


if __name__ == "__main__":
    main()
