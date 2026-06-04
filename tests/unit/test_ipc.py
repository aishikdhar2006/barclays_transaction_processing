# Copyright (c) Meta Platforms, Inc. and affiliates.
#
# This source code is licensed under the BSD license found in the
# LICENSE file in the root directory of this source tree.

from unittest.mock import patch

from banking_tools import ipc


class TestWrite:
    def test_no_channel_fd_does_nothing(self):
        # When NODE_CHANNEL_FD is -1 (default), _write returns without writing
        with patch.object(ipc, "NODE_CHANNEL_FD", -1):
            ipc._write({"test": "data"})  # Should not raise

    @patch("os.write")
    def test_unix_write(self, mock_write):
        with patch.object(ipc, "NODE_CHANNEL_FD", 5):
            with patch("os.name", "posix"):
                ipc._write({"key": "value"})
                mock_write.assert_called_once()
                data = mock_write.call_args[0][1]
                assert b"key" in data
                assert b"value" in data

    @patch("os.write")
    def test_windows_write_includes_header(self, mock_write):
        with patch.object(ipc, "NODE_CHANNEL_FD", 5):
            with patch("os.name", "nt"):
                ipc._write({"key": "value"})
                mock_write.assert_called_once()
                data = mock_write.call_args[0][1]
                # Windows includes 16-byte header
                assert len(data) > 16


class TestSend:
    def test_send_wraps_payload(self):
        with patch.object(ipc, "_write") as mock_write:
            ipc.send("upload_start", {"offset": 0})
            mock_write.assert_called_once()
            obj = mock_write.call_args[0][0]
            assert obj["type"] == "upload_start"
            assert obj["payload"] == {"offset": 0}

    def test_send_catches_exceptions(self, caplog):
        with patch.object(ipc, "_write", side_effect=OSError("broken pipe")):
            import logging

            with caplog.at_level(logging.WARNING):
                ipc.send("upload_progress", {})
            assert "IPC error" in caplog.text
