# Copyright (c) Meta Platforms, Inc. and affiliates.
#
# This source code is licensed under the BSD license found in the
# LICENSE file in the root directory of this source tree.

from unittest.mock import MagicMock, patch

import pytest
import requests

from banking_tools import api_v4


class TestHTTPContentError:
    def test_create(self):
        resp = MagicMock(spec=requests.Response)
        err = api_v4.HTTPContentError("bad content", resp)
        assert str(err) == "bad content"
        assert err.response is resp


class TestClusterFileType:
    def test_values(self):
        assert api_v4.ClusterFileType.ZIP.value == "zip"
        assert api_v4.ClusterFileType.BLACKVUE.value == "mly_blackvue_video"
        assert api_v4.ClusterFileType.CAMM.value == "mly_camm_video"


class TestIsAuthError:
    def test_401(self):
        resp = MagicMock(spec=requests.Response)
        resp.status_code = 401
        assert api_v4.is_auth_error(resp) is True

    def test_403(self):
        resp = MagicMock(spec=requests.Response)
        resp.status_code = 403
        assert api_v4.is_auth_error(resp) is True

    def test_400_not_authorized(self):
        resp = MagicMock(spec=requests.Response)
        resp.status_code = 400
        resp.json.return_value = {"debug_info": {"type": "NotAuthorizedError"}}
        assert api_v4.is_auth_error(resp) is True

    def test_400_other_type(self):
        resp = MagicMock(spec=requests.Response)
        resp.status_code = 400
        resp.json.return_value = {"debug_info": {"type": "OtherError"}}
        assert api_v4.is_auth_error(resp) is False

    def test_400_json_parse_error(self):
        resp = MagicMock(spec=requests.Response)
        resp.status_code = 400
        resp.json.side_effect = ValueError("bad json")
        assert api_v4.is_auth_error(resp) is False

    def test_200_not_auth(self):
        resp = MagicMock(spec=requests.Response)
        resp.status_code = 200
        assert api_v4.is_auth_error(resp) is False

    def test_500_not_auth(self):
        resp = MagicMock(spec=requests.Response)
        resp.status_code = 500
        assert api_v4.is_auth_error(resp) is False


class TestExtractAuthErrorMessage:
    def test_graph_api_message(self):
        resp = MagicMock(spec=requests.Response)
        resp.status_code = 401
        resp.json.return_value = {"error": {"message": "Token expired"}}
        result = api_v4.extract_auth_error_message(resp)
        assert result == "Token expired"

    def test_upload_service_message(self):
        resp = MagicMock(spec=requests.Response)
        resp.status_code = 401
        resp.json.return_value = {"debug_info": {"message": "Invalid token"}}
        result = api_v4.extract_auth_error_message(resp)
        assert result == "Invalid token"

    def test_fallback_text(self):
        resp = MagicMock(spec=requests.Response)
        resp.status_code = 401
        resp.json.return_value = {}
        resp.text = "Unauthorized"
        result = api_v4.extract_auth_error_message(resp)
        assert result == "Unauthorized"

    def test_json_parse_failure(self):
        resp = MagicMock(spec=requests.Response)
        resp.status_code = 401
        resp.json.side_effect = ValueError("not json")
        resp.text = "Error"
        result = api_v4.extract_auth_error_message(resp)
        assert result == "Error"


class TestJsonifyResponse:
    def test_valid_json(self):
        resp = MagicMock(spec=requests.Response)
        resp.json.return_value = {"data": "value"}
        resp.text = '{"data": "value"}'
        result = api_v4.jsonify_response(resp)
        assert result == {"data": "value"}

    def test_invalid_json_raises(self):
        resp = MagicMock(spec=requests.Response)
        resp.json.side_effect = requests.JSONDecodeError("not json", "doc", 0)
        resp.text = "not json"
        with pytest.raises(api_v4.HTTPContentError):
            api_v4.jsonify_response(resp)


class TestCreateUserSession:
    def test_creates_session_with_auth(self):
        session = api_v4.create_user_session("test_token_123")
        assert session.headers["Authorization"] == "OAuth test_token_123"
        session.close()


class TestCreateClientSession:
    def test_creates_session(self):
        session = api_v4.create_client_session()
        assert "Authorization" in session.headers
        session.close()

    def test_creates_session_disable_logging(self):
        session = api_v4.create_client_session(disable_logging=True)
        assert session.disable_logging_request is True
        assert session.disable_logging_response is True
        session.close()


class TestGetUploadToken:
    @patch.object(requests.Session, "post")
    def test_success(self, mock_post):
        mock_resp = MagicMock(spec=requests.Response)
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp
        session = api_v4.create_client_session()
        resp = api_v4.get_upload_token(session, "email@test.com", "password")
        assert resp is mock_resp
        session.close()


class TestFetchOrganization:
    @patch.object(requests.Session, "get")
    def test_success(self, mock_get):
        mock_resp = MagicMock(spec=requests.Response)
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp
        session = api_v4.create_user_session("tok")
        resp = api_v4.fetch_organization(session, "org123")
        assert resp is mock_resp
        session.close()


class TestFetchUserOrMe:
    @patch.object(requests.Session, "get")
    def test_me(self, mock_get):
        mock_resp = MagicMock(spec=requests.Response)
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp
        session = api_v4.create_user_session("tok")
        resp = api_v4.fetch_user_or_me(session)
        call_url = mock_get.call_args[0][0]
        assert "me" in call_url
        session.close()

    @patch.object(requests.Session, "get")
    def test_specific_user(self, mock_get):
        mock_resp = MagicMock(spec=requests.Response)
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp
        session = api_v4.create_user_session("tok")
        resp = api_v4.fetch_user_or_me(session, user_id="12345")
        call_url = mock_get.call_args[0][0]
        assert "12345" in call_url
        session.close()
