# Copyright (c) Meta Platforms, Inc. and affiliates.
#
# This source code is licensed under the BSD license found in the
# LICENSE file in the root directory of this source tree.

from pathlib import Path

import pytest

from banking_tools import processor


class TestUploadOptions:
    def test_default_values(self):
        user_items = {"user_upload_token": "tok", "MAPSettingsUserKey": "123"}
        opts = processor.UploadOptions(user_items=user_items)
        assert opts.chunk_size > 0
        assert opts.num_upload_workers > 0
        assert opts.dry_run is False

    def test_invalid_workers_raises(self):
        user_items = {"user_upload_token": "tok", "MAPSettingsUserKey": "123"}
        with pytest.raises(ValueError, match="num_upload_workers"):
            processor.UploadOptions(user_items=user_items, num_upload_workers=0)

    def test_invalid_chunk_size_raises(self):
        user_items = {"user_upload_token": "tok", "MAPSettingsUserKey": "123"}
        with pytest.raises(ValueError, match="chunk_size"):
            processor.UploadOptions(user_items=user_items, chunk_size=0)


class TestEventEmitter:
    def test_emit_no_listeners(self):
        emitter = processor.EventEmitter()
        # Should not raise
        emitter.emit("upload_start")

    def test_emit_with_listener(self):
        emitter = processor.EventEmitter()
        results = []

        @emitter.on("upload_start")
        def handler(data):
            results.append(data)

        emitter.emit("upload_start", {"test": True})
        assert len(results) == 1
        assert results[0] == {"test": True}

    def test_multiple_listeners(self):
        emitter = processor.EventEmitter()
        results = []

        @emitter.on("upload_progress")
        def handler1(data):
            results.append("h1")

        @emitter.on("upload_progress")
        def handler2(data):
            results.append("h2")

        emitter.emit("upload_progress", {})
        assert results == ["h1", "h2"]


class TestSequenceError:
    def test_is_exception(self):
        err = processor.SequenceError("test")
        assert isinstance(err, Exception)

    def test_exif_error(self):
        err = processor.ExifError("bad exif", Path("/tmp/img.jpg"))
        assert err.image_path == Path("/tmp/img.jpg")
        assert isinstance(err, processor.SequenceError)

    def test_invalid_zip_error(self):
        err = processor.InvalidBankingPlatformZipFileError("bad zip")
        assert isinstance(err, processor.SequenceError)


class TestUploadResult:
    def test_default(self):
        r = processor.UploadResult()
        assert r.result is None
        assert r.error is None

    def test_with_result(self):
        r = processor.UploadResult(result="success")
        assert r.result == "success"

    def test_with_error(self):
        r = processor.UploadResult(error=RuntimeError("fail"))
        assert r.error is not None


class TestUploader:
    def test_create_uploader(self):
        user_items = {"user_upload_token": "tok", "MAPSettingsUserKey": "123"}
        opts = processor.UploadOptions(user_items=user_items, dry_run=True)
        uploader = processor.Uploader(opts)
        assert uploader.upload_options == opts

    def test_emitter_property(self):
        user_items = {"user_upload_token": "tok", "MAPSettingsUserKey": "123"}
        opts = processor.UploadOptions(user_items=user_items, dry_run=True)
        uploader = processor.Uploader(opts)
        assert isinstance(uploader.emitter, processor.EventEmitter)


class TestImageSequenceUploader:
    def test_create(self):
        user_items = {"user_upload_token": "tok", "MAPSettingsUserKey": "123"}
        opts = processor.UploadOptions(user_items=user_items, dry_run=True)
        emitter = processor.EventEmitter()
        uploader = processor.ImageSequenceUploader(opts, emitter=emitter)
        assert uploader.upload_options == opts


class TestZipUploader:
    def test_upload_empty_list(self):
        user_items = {"user_upload_token": "tok", "MAPSettingsUserKey": "123"}
        opts = processor.UploadOptions(user_items=user_items, dry_run=True)
        uploader = processor.Uploader(opts)
        results = list(processor.ZipUploader.upload_zipfiles(uploader, []))
        assert results == []


class TestVideoUploader:
    def test_upload_empty_list(self):
        user_items = {"user_upload_token": "tok", "MAPSettingsUserKey": "123"}
        opts = processor.UploadOptions(user_items=user_items, dry_run=True)
        uploader = processor.Uploader(opts)
        results = list(processor.VideoUploader.upload_videos(uploader, []))
        assert results == []
