# Copyright (c) Meta Platforms, Inc. and affiliates.
#
# This source code is licensed under the BSD license found in the
# LICENSE file in the root directory of this source tree.

from unittest.mock import MagicMock, patch

import pytest
import requests

from banking_tools import http


class TestHTTPSystemCertsAdapter:
    def test_init(self):
        adapter = http.HTTPSystemCertsAdapter()
        assert adapter is not None

    def test_send_sets_cert_location(self):
        adapter = http.HTTPSystemCertsAdapter()
        request = MagicMock(spec=requests.PreparedRequest)
        request.url = "https://example.com"
        request.headers = {}
        request.body = None
        with patch.object(adapter, "send", wraps=adapter.send) as mock_send:
            pass


class TestSession:
    def test_session_creates(self):
        session = http.Session()
        assert isinstance(session, requests.Session)

    def test_session_has_custom_attrs(self):
        session = http.Session()
        assert hasattr(session, "disable_logging_request")
        assert hasattr(session, "disable_logging_response")

    @patch.object(requests.Session, "request")
    def test_request_success(self, mock_request):
        mock_response = MagicMock(spec=requests.Response)
        mock_response.status_code = 200
        mock_response.headers = {"Content-Type": "application/json"}
        mock_response.content = b'{"ok": true}'
        mock_response.url = "https://test.com/api"
        mock_request.return_value = mock_response
        session = http.Session()
        resp = session.request("GET", "https://test.com/api")
        assert resp.status_code == 200

    @patch.object(http.Session, "mount")
    @patch.object(requests.Session, "request")
    def test_request_ssl_error_retry(self, mock_request, mock_mount):
        ssl_error = requests.exceptions.SSLError(
            "SSLCertVerificationError: certificate verify failed"
        )
        mock_response = MagicMock(spec=requests.Response)
        mock_response.status_code = 200
        mock_response.headers = {}
        mock_response.content = b""
        mock_response.url = "https://test.com"
        mock_request.side_effect = [ssl_error, mock_response]
        original = http.Session.USE_SYSTEM_CERTS
        http.Session.USE_SYSTEM_CERTS = False
        try:
            session = http.Session()
            resp = session.request("GET", "https://test.com")
            assert resp.status_code == 200
            assert mock_request.call_count == 2
        finally:
            http.Session.USE_SYSTEM_CERTS = original

    @patch.object(requests.Session, "request")
    def test_request_ssl_error_non_cert_reraises(self, mock_request):
        ssl_error = requests.exceptions.SSLError("some other SSL problem")
        mock_request.side_effect = ssl_error
        original = http.Session.USE_SYSTEM_CERTS
        http.Session.USE_SYSTEM_CERTS = False
        try:
            session = http.Session()
            with pytest.raises(requests.exceptions.SSLError):
                session.request("GET", "https://test.com")
        finally:
            http.Session.USE_SYSTEM_CERTS = original

    @patch.object(requests.Session, "request")
    def test_request_logging_disabled(self, mock_request):
        mock_response = MagicMock(spec=requests.Response)
        mock_response.status_code = 200
        mock_response.headers = {}
        mock_response.content = b""
        mock_response.url = "https://test.com"
        mock_request.return_value = mock_response
        session = http.Session()
        session.disable_logging_request = True
        session.disable_logging_response = True
        resp = session.request("GET", "https://test.com")
        assert resp.status_code == 200


class TestReadableHttpError:
    def test_basic_error(self):
        resp = MagicMock(spec=requests.Response)
        resp.status_code = 404
        resp.reason = "Not Found"
        resp.url = "https://test.com/api"
        resp.headers = {"Content-Type": "text/plain"}
        resp.content = b"Not Found"
        resp.json.side_effect = requests.JSONDecodeError("err", "doc", 0)
        resp.request = MagicMock()
        resp.request.method = "GET"
        ex = requests.HTTPError(response=resp)
        result = http.readable_http_error(ex)
        assert "404" in result

    def test_json_error(self):
        resp = MagicMock(spec=requests.Response)
        resp.status_code = 400
        resp.reason = "Bad Request"
        resp.url = "https://test.com/api"
        resp.headers = {"Content-Type": "application/json"}
        resp.content = b'{"error": "bad request"}'
        resp.json.return_value = {"error": "bad request"}
        resp.request = MagicMock()
        resp.request.method = "POST"
        ex = requests.HTTPError(response=resp)
        result = http.readable_http_error(ex)
        assert isinstance(result, str)


class TestReadableHttpResponse:
    def test_basic(self):
        resp = MagicMock(spec=requests.Response)
        resp.status_code = 200
        resp.reason = "OK"
        resp.url = "https://test.com"
        resp.headers = {"Content-Type": "text/plain"}
        resp.content = b"OK"
        resp.json.side_effect = requests.JSONDecodeError("err", "doc", 0)
        resp.request = MagicMock()
        resp.request.method = "GET"
        result = http.readable_http_response(resp)
        assert "200" in result
