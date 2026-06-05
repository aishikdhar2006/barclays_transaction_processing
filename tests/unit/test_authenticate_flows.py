# Copyright (c) Meta Platforms, Inc. and affiliates.
#
# This source code is licensed under the BSD license found in the
# LICENSE file in the root directory of this source tree.

import typing as T
from unittest.mock import MagicMock, patch

import pytest
import requests

from banking_tools import authenticate, config, exceptions


def _user_items(token="tok") -> config.UserItem:
    return T.cast(
        config.UserItem,
        {"user_upload_token": token, "MAPSettingsUserKey": "uid"},
    )


class TestAuthenticate:
    @patch("banking_tools.authenticate.config.update_config")
    @patch("banking_tools.authenticate._verify_user_auth")
    @patch("banking_tools.authenticate.config.list_all_users")
    def test_jwt_new_profile(self, mock_list, mock_verify, mock_update):
        mock_list.return_value = {}
        mock_verify.return_value = _user_items()
        authenticate.authenticate(user_name="newprof", jwt="jwt-token")
        mock_update.assert_called_once()
        assert mock_update.call_args[0][0] == "newprof"

    @patch("banking_tools.authenticate.config.update_config")
    @patch("banking_tools.authenticate._verify_user_auth")
    @patch("banking_tools.authenticate.config.list_all_users")
    def test_jwt_existing_profile_overridden(self, mock_list, mock_verify, mock_update):
        mock_list.return_value = {"prof": _user_items()}
        mock_verify.return_value = _user_items()
        authenticate.authenticate(user_name="prof", jwt="jwt-token")
        mock_update.assert_called_once()

    @patch("banking_tools.authenticate.config.remove_config")
    @patch("banking_tools.authenticate.config.list_all_users")
    def test_delete_profile(self, mock_list, mock_remove):
        mock_list.return_value = {"prof": _user_items()}
        authenticate.authenticate(user_name="prof", delete=True)
        mock_remove.assert_called_once_with("prof")

    @patch("banking_tools.authenticate._prompt_enabled", return_value=False)
    @patch("banking_tools.authenticate.config.list_all_users")
    def test_no_profile_name_no_prompt_raises(self, mock_list, _mock_prompt):
        mock_list.return_value = {}
        with pytest.raises(exceptions.BankingPlatformBadParameterError):
            authenticate.authenticate()

    @patch("banking_tools.authenticate.config.update_config")
    @patch("banking_tools.authenticate._validate_profile")
    @patch("banking_tools.authenticate._prompt_login")
    @patch("banking_tools.authenticate.config.list_all_users")
    def test_login_flow(self, mock_list, mock_login, mock_validate, mock_update):
        mock_list.return_value = {}
        mock_login.return_value = _user_items()
        authenticate.authenticate(
            user_name="prof", user_email="a@b.com", user_password="pw"
        )
        mock_login.assert_called_once()
        mock_update.assert_called_once()


class TestFetchUserItems:
    @patch("banking_tools.authenticate._verify_user_auth")
    @patch("banking_tools.authenticate.config.list_all_users")
    def test_single_profile(self, mock_list, mock_verify):
        mock_list.return_value = {"prof": _user_items()}
        mock_verify.side_effect = lambda x: x
        result = authenticate.fetch_user_items()
        assert result["user_upload_token"] == "tok"

    @patch("banking_tools.authenticate._verify_user_auth")
    @patch("banking_tools.authenticate.config.list_all_users")
    def test_named_profile(self, mock_list, mock_verify):
        mock_list.return_value = {"a": _user_items("a"), "b": _user_items("b")}
        mock_verify.side_effect = lambda x: x
        result = authenticate.fetch_user_items(user_name="b")
        assert result["user_upload_token"] == "b"

    @patch("banking_tools.authenticate.config.list_all_users")
    def test_named_profile_not_found(self, mock_list):
        mock_list.return_value = {"a": _user_items("a")}
        with pytest.raises(exceptions.BankingPlatformBadParameterError):
            authenticate.fetch_user_items(user_name="missing")

    @patch("banking_tools.authenticate._prompt_enabled", return_value=False)
    @patch("banking_tools.authenticate.config.list_all_users")
    def test_multiple_profiles_no_prompt_raises(self, mock_list, _mock_prompt):
        mock_list.return_value = {"a": _user_items("a"), "b": _user_items("b")}
        with pytest.raises(exceptions.BankingPlatformBadParameterError):
            authenticate.fetch_user_items()

    @patch("banking_tools.authenticate.api_v4.jsonify_response")
    @patch("banking_tools.authenticate.api_v4.fetch_organization")
    @patch("banking_tools.authenticate.api_v4.create_user_session")
    @patch("banking_tools.authenticate._verify_user_auth")
    @patch("banking_tools.authenticate.config.list_all_users")
    def test_with_organization_key(
        self, mock_list, mock_verify, mock_session, mock_fetch, mock_json
    ):
        mock_list.return_value = {"prof": _user_items()}
        mock_verify.side_effect = lambda x: x
        mock_session.return_value.__enter__ = MagicMock()
        mock_session.return_value.__exit__ = MagicMock(return_value=False)
        mock_json.return_value = {"name": "Org", "id": "org123"}
        result = authenticate.fetch_user_items(organization_key="org123")
        assert result["MAPOrganizationKey"] == "org123"

    @patch("banking_tools.authenticate._verify_user_auth")
    @patch("banking_tools.authenticate.config.list_all_users")
    def test_timeout_wrapped(self, mock_list, mock_verify):
        mock_list.return_value = {"prof": _user_items()}
        mock_verify.side_effect = requests.Timeout("slow")
        with pytest.raises(exceptions.BankingPlatformUploadTimeoutError):
            authenticate.fetch_user_items()

    @patch("banking_tools.authenticate._verify_user_auth")
    @patch("banking_tools.authenticate.config.list_all_users")
    def test_connection_error_wrapped(self, mock_list, mock_verify):
        mock_list.return_value = {"prof": _user_items()}
        mock_verify.side_effect = requests.ConnectionError("down")
        with pytest.raises(exceptions.BankingPlatformUploadConnectionError):
            authenticate.fetch_user_items()


class TestPromptChooseProfileName:
    @patch("banking_tools.authenticate._prompt_enabled", return_value=True)
    @patch("banking_tools.authenticate._prompt")
    def test_existing_match(self, mock_prompt, _mock_enabled):
        mock_prompt.return_value = "prof1"
        result = authenticate._prompt_choose_profile_name(["prof1", "prof2"])
        assert result == "prof1"

    @patch("banking_tools.authenticate._prompt_enabled", return_value=True)
    @patch("banking_tools.authenticate._prompt")
    def test_index_match(self, mock_prompt, _mock_enabled):
        mock_prompt.return_value = "2"
        result = authenticate._prompt_choose_profile_name(["prof1", "prof2"])
        assert result == "prof2"

    @patch("banking_tools.authenticate._prompt_enabled", return_value=True)
    @patch("banking_tools.authenticate._prompt")
    def test_must_exist_not_found_then_found(self, mock_prompt, _mock_enabled):
        mock_prompt.side_effect = ["nope", "prof1"]
        result = authenticate._prompt_choose_profile_name(["prof1"], must_exist=True)
        assert result == "prof1"

    @patch("banking_tools.authenticate._prompt_enabled", return_value=True)
    @patch("banking_tools.authenticate._prompt")
    def test_new_valid_profile_name(self, mock_prompt, _mock_enabled):
        mock_prompt.return_value = "brandnew"
        result = authenticate._prompt_choose_profile_name(["existing"])
        assert result == "brandnew"


class TestPromptLoginErrors:
    @patch("banking_tools.authenticate.api_v4.get_upload_token")
    @patch("banking_tools.authenticate.api_v4.create_client_session")
    @patch("banking_tools.authenticate._prompt_enabled", return_value=False)
    def test_http_error_not_enabled_reraises(
        self, _mock_enabled, mock_session, mock_token
    ):
        mock_session.return_value.__enter__ = MagicMock()
        mock_session.return_value.__exit__ = MagicMock(return_value=False)

        resp = requests.Response()
        resp.status_code = 400
        mock_token.side_effect = requests.HTTPError("bad", response=resp)

        with pytest.raises(requests.HTTPError):
            authenticate._prompt_login(user_email="a@b.com", user_password="pw")


class TestIsLoginRetryableExtra:
    def test_retryable_subcode_true(self):
        resp = MagicMock()
        resp.status_code = 400
        resp.json.return_value = {
            "error": {
                "error_subcode": 1348028,
                "error_user_title": "title",
                "error_user_msg": "msg",
            }
        }
        ex = requests.HTTPError("e", response=resp)
        assert authenticate._is_login_retryable(ex) is True

    def test_non_retryable_subcode_false(self):
        resp = MagicMock()
        resp.status_code = 400
        resp.json.return_value = {"error": {"error_subcode": 999}}
        ex = requests.HTTPError("e", response=resp)
        assert authenticate._is_login_retryable(ex) is False
