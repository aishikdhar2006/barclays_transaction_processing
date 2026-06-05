# Copyright (c) Meta Platforms, Inc. and affiliates.
#
# This source code is licensed under the BSD license found in the
# LICENSE file in the root directory of this source tree.

import typing as T
from unittest.mock import MagicMock, patch

import py.path
import pytest
import requests

from banking_tools import config, constants, exceptions
from banking_tools.authenticate import (
    _is_interactive,
    _is_login_retryable,
    _list_all_profiles,
    _prompt_enabled,
    _prompt_login,
    _validate_profile,
    _validate_profile_name,
    _verify_user_auth,
    _welcome,
    authenticate,
    fetch_user_items,
)


class TestValidateProfileName:
    def test_valid_name(self):
        _validate_profile_name("myprofile")

    def test_valid_name_with_numbers(self):
        _validate_profile_name("user123")

    def test_valid_name_with_hyphens_underscores(self):
        _validate_profile_name("my-user_name")

    def test_too_short(self):
        with pytest.raises(
            exceptions.BankingPlatformBadParameterError, match="between 2 and 32"
        ):
            _validate_profile_name("a")

    def test_too_long(self):
        with pytest.raises(
            exceptions.BankingPlatformBadParameterError, match="between 2 and 32"
        ):
            _validate_profile_name("a" * 33)

    def test_starts_with_number(self):
        with pytest.raises(
            exceptions.BankingPlatformBadParameterError, match="Invalid profile"
        ):
            _validate_profile_name("1invalid")

    def test_special_characters(self):
        with pytest.raises(
            exceptions.BankingPlatformBadParameterError, match="Invalid profile"
        ):
            _validate_profile_name("ab@cd")


class TestValidateProfile:
    def test_valid_profile(self):
        user_items: config.UserItem = {"user_upload_token": "test_token"}
        result = _validate_profile(user_items)
        assert result == user_items

    def test_invalid_profile_missing_token(self):
        with pytest.raises(
            exceptions.BankingPlatformBadParameterError, match="Invalid profile"
        ):
            _validate_profile(T.cast(config.UserItem, {}))


class TestVerifyUserAuth:
    def test_verification_disabled(self):
        user_items: config.UserItem = {"user_upload_token": "tok"}
        with patch.object(constants, "_AUTH_VERIFICATION_DISABLED", True):
            result = _verify_user_auth(user_items)
        assert result == user_items

    @patch("banking_tools.authenticate.api_v4.create_user_session")
    @patch("banking_tools.authenticate.api_v4.fetch_user_or_me")
    @patch("banking_tools.authenticate.api_v4.jsonify_response")
    def test_verification_success(self, mock_json, mock_fetch, mock_session):
        mock_session.return_value.__enter__ = MagicMock()
        mock_session.return_value.__exit__ = MagicMock(return_value=False)
        mock_json.return_value = {"username": "testuser", "id": "12345"}
        with patch.object(constants, "_AUTH_VERIFICATION_DISABLED", False):
            result = _verify_user_auth({"user_upload_token": "tok"})
        assert result["MAPSettingsUsername"] == "testuser"
        assert result["MAPSettingsUserKey"] == "12345"

    @patch("banking_tools.authenticate.api_v4.create_user_session")
    @patch("banking_tools.authenticate.api_v4.fetch_user_or_me")
    def test_verification_auth_error(self, mock_fetch, mock_session):
        mock_session.return_value.__enter__ = MagicMock()
        mock_session.return_value.__exit__ = MagicMock(return_value=False)
        resp = MagicMock(spec=requests.Response)
        resp.status_code = 401
        resp.json.return_value = {}
        resp.text = "Unauthorized"
        mock_fetch.side_effect = requests.HTTPError(response=resp)
        with patch.object(constants, "_AUTH_VERIFICATION_DISABLED", False):
            with pytest.raises(exceptions.BankingPlatformUploadUnauthorizedError):
                _verify_user_auth({"user_upload_token": "tok"})

    @patch("banking_tools.authenticate.api_v4.create_user_session")
    @patch("banking_tools.authenticate.api_v4.fetch_user_or_me")
    def test_verification_non_auth_http_error(self, mock_fetch, mock_session):
        mock_session.return_value.__enter__ = MagicMock()
        mock_session.return_value.__exit__ = MagicMock(return_value=False)
        resp = MagicMock(spec=requests.Response)
        resp.status_code = 500
        resp.json.return_value = {}
        mock_fetch.side_effect = requests.HTTPError(response=resp)
        with patch.object(constants, "_AUTH_VERIFICATION_DISABLED", False):
            with pytest.raises(requests.HTTPError):
                _verify_user_auth({"user_upload_token": "tok"})


class TestIsInteractive:
    @patch("sys.stdout")
    @patch("sys.stdin")
    @patch("sys.stderr")
    def test_non_interactive(self, mock_err, mock_in, mock_out):
        mock_out.isatty.return_value = False
        mock_in.isatty.return_value = False
        mock_err.isatty.return_value = False
        assert _is_interactive() is False


class TestPromptEnabled:
    def test_disabled_via_constant(self):
        with patch.object(constants, "PROMPT_DISABLED", True):
            assert _prompt_enabled() is False

    def test_disabled_non_interactive(self):
        with (
            patch.object(constants, "PROMPT_DISABLED", False),
            patch("banking_tools.authenticate._is_interactive", return_value=False),
        ):
            assert _prompt_enabled() is False


class TestIsLoginRetryable:
    def test_retryable_subcode(self):
        resp = MagicMock(spec=requests.Response)
        resp.status_code = 400
        resp.json.return_value = {
            "error": {
                "error_subcode": 1348028,
                "error_user_title": "T",
                "error_user_msg": "M",
            }
        }
        ex = requests.HTTPError(response=resp)
        assert _is_login_retryable(ex) is True

    def test_non_retryable_subcode(self):
        resp = MagicMock(spec=requests.Response)
        resp.status_code = 400
        resp.json.return_value = {"error": {"error_subcode": 9999}}
        ex = requests.HTTPError(response=resp)
        assert _is_login_retryable(ex) is False

    def test_server_error_not_retryable(self):
        resp = MagicMock(spec=requests.Response)
        resp.status_code = 500
        ex = requests.HTTPError(response=resp)
        assert _is_login_retryable(ex) is False


class TestListAllProfiles:
    def test_list_profiles(self, capsys):
        profiles = {
            "user1": {"MAPSettingsUserKey": "123", "MAPSettingsUsername": "alice"},
            "user2": {},
        }
        _list_all_profiles(profiles)
        captured = capsys.readouterr()
        assert "user1" in captured.err
        assert "alice" in captured.err
        assert "user2" in captured.err


class TestWelcome:
    def test_welcome_message(self, capsys):
        _welcome()
        captured = capsys.readouterr()
        assert "Welcome to BankingPlatform" in captured.err


class TestPromptLogin:
    def test_no_email_no_prompt_raises(self):
        with patch("banking_tools.authenticate._prompt_enabled", return_value=False):
            with pytest.raises(
                exceptions.BankingPlatformBadParameterError, match="user_email"
            ):
                _prompt_login(user_email=None, user_password="pass")

    def test_no_password_no_prompt_raises(self):
        with patch("banking_tools.authenticate._prompt_enabled", return_value=False):
            with pytest.raises(
                exceptions.BankingPlatformBadParameterError, match="user_password"
            ):
                _prompt_login(user_email="test@test.com", user_password=None)

    @patch("banking_tools.authenticate.api_v4.create_client_session")
    @patch("banking_tools.authenticate.api_v4.get_upload_token")
    @patch("banking_tools.authenticate.api_v4.jsonify_response")
    def test_successful_login(self, mock_json, mock_token, mock_session):
        mock_session.return_value.__enter__ = MagicMock()
        mock_session.return_value.__exit__ = MagicMock(return_value=False)
        mock_json.return_value = {"access_token": "at123", "user_id": "uid456"}
        result = _prompt_login(user_email="test@test.com", user_password="pass")
        assert result["user_upload_token"] == "at123"
        assert result["MAPSettingsUserKey"] == "uid456"


class TestFetchUserItems:
    def test_with_user_name_from_config(self, tmpdir: py.path.local):
        c = tmpdir.join("config.ini")
        with patch.object(config, "MAPILLARY_CONFIG_PATH", str(c)):
            config.update_config(
                "testuser",
                T.cast(config.UserItem, {"user_upload_token": "saved_token"}),
            )
            with patch.object(constants, "_AUTH_VERIFICATION_DISABLED", True):
                result = fetch_user_items(user_name="testuser")
        assert result["user_upload_token"] == "saved_token"

    def test_with_user_name_not_found(self, tmpdir: py.path.local):
        c = tmpdir.join("config.ini")
        with patch.object(config, "MAPILLARY_CONFIG_PATH", str(c)):
            config.update_config(
                "existing",
                T.cast(config.UserItem, {"user_upload_token": "tok"}),
            )
            with patch(
                "banking_tools.authenticate._prompt_enabled", return_value=False
            ):
                with pytest.raises(
                    exceptions.BankingPlatformBadParameterError, match="not found"
                ):
                    fetch_user_items(user_name="nonexistent")


class TestAuthenticate:
    @patch("banking_tools.authenticate._prompt_login")
    @patch("banking_tools.authenticate._verify_user_auth")
    def test_authenticate_with_jwt(
        self, mock_verify, mock_login, tmpdir: py.path.local
    ):
        c = tmpdir.join("config.ini")
        mock_verify.return_value = {
            "user_upload_token": "jwt_tok",
            "MAPSettingsUserKey": "key1",
            "MAPSettingsUsername": "user1",
        }
        with patch.object(config, "MAPILLARY_CONFIG_PATH", str(c)):
            authenticate(
                user_name="myprofile",
                jwt="jwt_tok",
            )
            assert config.load_user("myprofile") is not None
        mock_login.assert_not_called()
        mock_verify.assert_called_once()
