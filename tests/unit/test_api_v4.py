# Copyright (c) Meta Platforms, Inc. and affiliates.
#
# This source code is licensed under the BSD license found in the
# LICENSE file in the root directory of this source tree.

from unittest.mock import MagicMock

import pytest
import requests

from banking_tools import api_v4


class TestCreateSessions:
    def test_create_user_session(self):
        session = api_v4.create_user_session("my_token")
        assert session.headers["Authorization"] == "OAuth my_token"
        session.close()

    def test_create_client_session(self):
        session = api_v4.create_client_session()
        assert (
            session.headers["Authorization"] == f"OAuth {api_v4.MAPILLARY_CLIENT_TOKEN}"
        )
        session.close()

    def test_create_client_session_disable_logging(self):
        session = api_v4.create_client_session(disable_logging=True)
        assert session.disable_logging_request is True
        assert session.disable_logging_response is True
        session.close()


class TestIsAuthError:
    def test_401_is_auth_error(self):
        resp = MagicMock(spec=requests.Response)
        resp.status_code = 401
        assert api_v4.is_auth_error(resp) is True

    def test_403_is_auth_error(self):
        resp = MagicMock(spec=requests.Response)
        resp.status_code = 403
        assert api_v4.is_auth_error(resp) is True

    def test_400_with_not_authorized_type(self):
        resp = MagicMock(spec=requests.Response)
        resp.status_code = 400
        resp.json.return_value = {"debug_info": {"type": "NotAuthorizedError"}}
        assert api_v4.is_auth_error(resp) is True

    def test_400_with_other_type(self):
        resp = MagicMock(spec=requests.Response)
        resp.status_code = 400
        resp.json.return_value = {"debug_info": {"type": "ValidationError"}}
        assert api_v4.is_auth_error(resp) is False

    def test_200_not_auth_error(self):
        resp = MagicMock(spec=requests.Response)
        resp.status_code = 200
        assert api_v4.is_auth_error(resp) is False


class TestExtractAuthErrorMessage:
    def test_graph_api_error_message(self):
        resp = MagicMock(spec=requests.Response)
        resp.status_code = 401
        resp.json.return_value = {"error": {"message": "Token expired"}}
        result = api_v4.extract_auth_error_message(resp)
        assert result == "Token expired"

    def test_upload_service_message(self):
        resp = MagicMock(spec=requests.Response)
        resp.status_code = 401
        resp.json.return_value = {"debug_info": {"message": "Invalid auth"}}
        result = api_v4.extract_auth_error_message(resp)
        assert result == "Invalid auth"

    def test_falls_back_to_text(self):
        resp = MagicMock(spec=requests.Response)
        resp.status_code = 401
        resp.json.return_value = {}
        resp.text = "Unauthorized"
        result = api_v4.extract_auth_error_message(resp)
        assert result == "Unauthorized"


class TestHTTPContentError:
    def test_creation(self):
        resp = MagicMock(spec=requests.Response)
        ex = api_v4.HTTPContentError("bad content", resp)
        assert ex.response is resp
        assert str(ex) == "bad content"


class TestJsonifyResponse:
    def test_valid_json(self):
        resp = MagicMock(spec=requests.Response)
        resp.json.return_value = {"key": "value"}
        result = api_v4.jsonify_response(resp)
        assert result == {"key": "value"}

    def test_invalid_json(self):
        resp = MagicMock(spec=requests.Response)
        resp.json.side_effect = requests.JSONDecodeError("", "", 0)
        resp.text = "not json"
        with pytest.raises(api_v4.HTTPContentError):
            api_v4.jsonify_response(resp)


class TestClusterFileType:
    def test_values(self):
        assert api_v4.ClusterFileType.ZIP.value == "zip"
        assert api_v4.ClusterFileType.CAMM.value == "mly_camm_video"
