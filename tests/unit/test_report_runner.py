# Copyright (c) Meta Platforms, Inc. and affiliates.
#
# This source code is licensed under the BSD license found in the
# LICENSE file in the root directory of this source tree.

from unittest.mock import MagicMock, patch

import pytest

from banking_tools import report_runner


class TestExiftoolRunner:
    def test_init_defaults(self):
        runner = report_runner.ExiftoolRunner()
        assert runner.exiftool_executable == "exiftool"
        assert runner.recursive is False

    def test_init_custom(self):
        runner = report_runner.ExiftoolRunner(
            exiftool_executable="/usr/bin/exiftool", recursive=True
        )
        assert runner.exiftool_executable == "/usr/bin/exiftool"
        assert runner.recursive is True

    def test_build_args_basic(self):
        runner = report_runner.ExiftoolRunner()
        args = runner._build_args_read_stdin()
        assert "exiftool" in args
        assert "-fast" in args
        assert "-X" in args
        assert "-r" not in args

    def test_build_args_recursive(self):
        runner = report_runner.ExiftoolRunner(recursive=True)
        args = runner._build_args_read_stdin()
        assert "-r" in args

    def test_extract_xml_empty_paths_raises(self):
        runner = report_runner.ExiftoolRunner()
        with pytest.raises(ValueError, match="No files provided"):
            runner.extract_xml([])

    @patch("subprocess.run")
    def test_extract_xml_returns_stdout(self, mock_run, tmp_path):
        mock_result = MagicMock()
        mock_result.stdout = "<xml>test</xml>"
        mock_run.return_value = mock_result

        img = tmp_path / "test.jpg"
        img.touch()

        runner = report_runner.ExiftoolRunner()
        result = runner.extract_xml([img])
        assert result == "<xml>test</xml>"
        mock_run.assert_called_once()

    @patch("subprocess.run")
    def test_extract_xml_passes_paths_via_stdin(self, mock_run, tmp_path):
        mock_result = MagicMock()
        mock_result.stdout = ""
        mock_run.return_value = mock_result

        img1 = tmp_path / "a.jpg"
        img2 = tmp_path / "b.jpg"
        img1.touch()
        img2.touch()

        runner = report_runner.ExiftoolRunner()
        runner.extract_xml([img1, img2])

        call_kwargs = mock_run.call_args[1]
        assert str(img1.resolve()) in call_kwargs["input"]
        assert str(img2.resolve()) in call_kwargs["input"]
