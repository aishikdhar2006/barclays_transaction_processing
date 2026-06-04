# Copyright (c) Meta Platforms, Inc. and affiliates.
#
# This source code is licensed under the BSD license found in the
# LICENSE file in the root directory of this source tree.

import datetime
import logging
from unittest.mock import MagicMock, patch

import requests

from banking_tools import http


def _make_mock_response(status_code=200, reason="OK", content=b""):
    resp = MagicMock(spec=requests.Response)
    resp.status_code = status_code
    resp.reason = reason
    resp.content = content
    resp.elapsed = datetime.timedelta(milliseconds=100)
    resp.json.side_effect = requests.JSONDecodeError("", "", 0)
    return resp


class TestSession:
    def setup_method(self):
        # Reset class variable between tests
        http.Session.USE_SYSTEM_CERTS = False

    def test_request_normal(self):
        session = http.Session()
        with patch.object(requests.Session, "request") as mock_req:
            mock_resp = _make_mock_response()
            mock_req.return_value = mock_resp

            resp = session.request("GET", "https://example.com")
            assert resp.status_code == 200

    def test_request_ssl_error_falls_back(self):
        session = http.Session()
        call_count = [0]

        def side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                raise requests.exceptions.SSLError("SSLCertVerificationError")
            return _make_mock_response()

        with patch.object(requests.Session, "request", side_effect=side_effect):
            resp = session.request("GET", "https://example.com")
            assert resp.status_code == 200
            assert http.Session.USE_SYSTEM_CERTS is True

    def test_request_ssl_error_non_cert_reraises(self):
        session = http.Session()
        with patch.object(requests.Session, "request") as mock_req:
            mock_req.side_effect = requests.exceptions.SSLError("Connection reset")
            import pytest

            with pytest.raises(requests.exceptions.SSLError):
                session.request("GET", "https://example.com")

    def test_disable_logging_request(self, caplog):
        session = http.Session()
        session.disable_logging_request = True
        with patch.object(requests.Session, "request") as mock_req:
            mock_req.return_value = _make_mock_response()

            with caplog.at_level(logging.DEBUG):
                session.request("GET", "https://example.com")
            # Should not have logged the request
            assert "HTTP GET" not in caplog.text

    def test_disable_logging_response(self, caplog):
        session = http.Session()
        session.disable_logging_response = True
        with patch.object(requests.Session, "request") as mock_req:
            mock_req.return_value = _make_mock_response()

            with caplog.at_level(logging.DEBUG):
                session.request("GET", "https://example.com")
            # Should not have logged the response
            assert "HTTP 200" not in caplog.text

    def test_log_debug_request_with_json(self, caplog):
        session = http.Session()
        session.disable_logging_response = True
        with patch.object(requests.Session, "request") as mock_req:
            mock_req.return_value = _make_mock_response()

            with caplog.at_level(logging.DEBUG, logger="banking_tools"):
                session.request("POST", "https://api.com/upload", json={"key": "val"})
            assert "JSON=" in caplog.text

    def test_log_debug_request_with_params(self, caplog):
        session = http.Session()
        session.disable_logging_response = True
        with patch.object(requests.Session, "request") as mock_req:
            mock_req.return_value = _make_mock_response()

            with caplog.at_level(logging.DEBUG, logger="banking_tools"):
                session.request("GET", "https://api.com", params={"q": "test"})
            assert "PARAMS=" in caplog.text

    def test_log_debug_request_with_timeout(self, caplog):
        session = http.Session()
        session.disable_logging_response = True
        with patch.object(requests.Session, "request") as mock_req:
            mock_req.return_value = _make_mock_response()

            with caplog.at_level(logging.DEBUG, logger="banking_tools"):
                session.request("GET", "https://api.com", timeout=30)
            assert "TIMEOUT=30" in caplog.text


class TestReadableHttpError:
    def test_readable_error(self):
        resp = MagicMock(spec=requests.Response)
        resp.status_code = 404
        resp.reason = "Not Found"
        resp.url = "https://api.com/resource"
        resp.content = b"not found"
        resp.request = MagicMock()
        resp.request.method = "GET"
        resp.json.side_effect = requests.JSONDecodeError("", "", 0)
        err = requests.HTTPError(response=resp)

        result = http.readable_http_error(err)
        assert "404" in result
        assert "GET" in result
        assert "https://api.com/resource" in result

    def test_readable_response(self):
        resp = MagicMock(spec=requests.Response)
        resp.status_code = 500
        resp.reason = "Internal Server Error"
        resp.url = "https://api.com/upload"
        resp.content = b"error"
        resp.request = MagicMock()
        resp.request.method = "POST"
        resp.json.side_effect = requests.JSONDecodeError("", "", 0)

        result = http.readable_http_response(resp)
        assert "500" in result
        assert "POST" in result
