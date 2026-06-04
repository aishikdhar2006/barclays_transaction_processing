# Copyright (c) Meta Platforms, Inc. and affiliates.
#
# This source code is licensed under the BSD license found in the
# LICENSE file in the root directory of this source tree.

from unittest.mock import MagicMock, patch

import pytest
import requests

from banking_tools import api_v4, authenticate, config, constants, exceptions


class TestValidateProfileName:
    def test_valid_name(self):
        # Should not raise
        authenticate._validate_profile_name("myprofile")

    def test_valid_name_with_numbers(self):
        authenticate._validate_profile_name("profile123")

    def test_valid_name_with_hyphens(self):
        authenticate._validate_profile_name("my-profile")

    def test_valid_name_with_underscores(self):
        authenticate._validate_profile_name("my_profile")

    def test_too_short(self):
        with pytest.raises(exceptions.BankingPlatformBadParameterError):
            authenticate._validate_profile_name("a")

    def test_too_long(self):
        with pytest.raises(exceptions.BankingPlatformBadParameterError):
            authenticate._validate_profile_name("a" * 33)

    def test_starts_with_number(self):
        with pytest.raises(exceptions.BankingPlatformBadParameterError):
            authenticate._validate_profile_name("1profile")

    def test_special_characters(self):
        with pytest.raises(exceptions.BankingPlatformBadParameterError):
            authenticate._validate_profile_name("pro file")

    def test_starts_with_hyphen(self):
        with pytest.raises(exceptions.BankingPlatformBadParameterError):
            authenticate._validate_profile_name("-profile")


class TestValidateProfile:
    @patch.object(config.UserItemSchemaValidator, "validate")
    def test_valid_profile(self, mock_validate):
        user_items = {"user_upload_token": "tok123"}
        result = authenticate._validate_profile(user_items)
        assert result == user_items
        mock_validate.assert_called_once_with(user_items)

    @patch.object(config.UserItemSchemaValidator, "validate")
    def test_invalid_profile_raises(self, mock_validate):
        import jsonschema

        mock_validate.side_effect = jsonschema.ValidationError("bad format")
        with pytest.raises(
            exceptions.BankingPlatformBadParameterError, match="Invalid profile format"
        ):
            authenticate._validate_profile({"bad": "data"})


class TestVerifyUserAuth:
    @patch.object(constants, "_AUTH_VERIFICATION_DISABLED", True)
    def test_verification_disabled(self):
        user_items = {"user_upload_token": "tok"}
        result = authenticate._verify_user_auth(user_items)
        assert result == user_items

    @patch("banking_tools.api_v4.create_user_session")
    @patch("banking_tools.api_v4.fetch_user_or_me")
    @patch("banking_tools.api_v4.jsonify_response")
    def test_verification_success(self, mock_jsonify, mock_fetch, mock_session):
        mock_session.return_value.__enter__ = MagicMock()
        mock_session.return_value.__exit__ = MagicMock(return_value=False)
        mock_jsonify.return_value = {"username": "testuser", "id": "12345"}

        user_items = {"user_upload_token": "tok"}
        with patch.object(constants, "_AUTH_VERIFICATION_DISABLED", False):
            result = authenticate._verify_user_auth(user_items)
        assert result["MAPSettingsUsername"] == "testuser"
        assert result["MAPSettingsUserKey"] == "12345"

    @patch("banking_tools.api_v4.create_user_session")
    @patch("banking_tools.api_v4.fetch_user_or_me")
    def test_verification_auth_error(self, mock_fetch, mock_session):
        mock_session.return_value.__enter__ = MagicMock()
        mock_session.return_value.__exit__ = MagicMock(return_value=False)
        resp = MagicMock(spec=requests.Response)
        resp.status_code = 401
        http_err = requests.HTTPError(response=resp)
        mock_fetch.side_effect = http_err

        with patch.object(constants, "_AUTH_VERIFICATION_DISABLED", False):
            with patch.object(api_v4, "is_auth_error", return_value=True):
                with patch.object(
                    api_v4, "extract_auth_error_message", return_value="bad token"
                ):
                    with pytest.raises(
                        exceptions.BankingPlatformUploadUnauthorizedError
                    ):
                        authenticate._verify_user_auth({"user_upload_token": "bad"})


class TestIsInteractive:
    @patch("sys.stdout")
    @patch("sys.stdin")
    @patch("sys.stderr")
    def test_not_interactive(self, mock_stderr, mock_stdin, mock_stdout):
        mock_stdout.isatty = MagicMock(return_value=False)
        mock_stdin.isatty = MagicMock(return_value=False)
        mock_stderr.isatty = MagicMock(return_value=False)
        assert authenticate._is_interactive() is False


class TestPromptEnabled:
    def test_disabled_when_constant_set(self):
        with patch.object(constants, "PROMPT_DISABLED", True):
            assert authenticate._prompt_enabled() is False


class TestIsLoginRetryable:
    def test_retryable_subcode(self):
        resp = MagicMock(spec=requests.Response)
        resp.status_code = 400
        resp.json.return_value = {
            "error": {
                "error_subcode": 1348028,
                "error_user_title": "Try Again",
                "error_user_msg": "Please retry",
            }
        }
        err = requests.HTTPError(response=resp)
        assert authenticate._is_login_retryable(err) is True

    def test_not_retryable_subcode(self):
        resp = MagicMock(spec=requests.Response)
        resp.status_code = 400
        resp.json.return_value = {"error": {"error_subcode": 9999}}
        err = requests.HTTPError(response=resp)
        assert authenticate._is_login_retryable(err) is False

    def test_not_retryable_5xx(self):
        resp = MagicMock(spec=requests.Response)
        resp.status_code = 500
        err = requests.HTTPError(response=resp)
        assert authenticate._is_login_retryable(err) is False


class TestListAllProfiles:
    def test_lists_profiles(self, capsys):
        profiles = {
            "default": {"MAPSettingsUserKey": "123", "MAPSettingsUsername": "john"},
            "work": {"MAPSettingsUserKey": "456", "MAPSettingsUsername": "jane"},
        }
        authenticate._list_all_profiles(profiles)
        captured = capsys.readouterr()
        assert "default" in captured.err
        assert "work" in captured.err
        assert "123" in captured.err
        assert "456" in captured.err


class TestWelcome:
    def test_welcome_message(self, capsys):
        authenticate._welcome()
        captured = capsys.readouterr()
        assert "Welcome to BankingPlatform" in captured.err


class TestFetchUserItems:
    @patch("banking_tools.config.list_all_users")
    @patch("banking_tools.authenticate.authenticate")
    @patch("banking_tools.authenticate._verify_user_auth")
    @patch("banking_tools.authenticate._validate_profile")
    def test_single_profile_auto_select(
        self, mock_validate, mock_verify, mock_auth, mock_list
    ):
        user_items = {"user_upload_token": "tok", "MAPSettingsUserKey": "123"}
        mock_list.side_effect = [
            {"default": user_items},
            {"default": user_items},
        ]
        mock_validate.return_value = user_items
        mock_verify.return_value = user_items

        result = authenticate.fetch_user_items()
        assert result == user_items

    @patch("banking_tools.config.list_all_users")
    @patch("banking_tools.authenticate._verify_user_auth")
    @patch("banking_tools.authenticate._validate_profile")
    def test_named_profile(self, mock_validate, mock_verify, mock_list):
        user_items = {"user_upload_token": "tok"}
        mock_list.return_value = {"myprofile": user_items}
        mock_validate.return_value = user_items
        mock_verify.return_value = user_items

        result = authenticate.fetch_user_items(user_name="myprofile")
        assert result == user_items

    @patch("banking_tools.config.list_all_users")
    def test_profile_not_found(self, mock_list):
        mock_list.return_value = {"existing": {"user_upload_token": "tok"}}
        with pytest.raises(
            exceptions.BankingPlatformBadParameterError, match="not found"
        ):
            authenticate.fetch_user_items(user_name="nonexistent")


class TestAuthenticate:
    @patch("banking_tools.config.list_all_users")
    @patch("banking_tools.config.update_config")
    @patch("banking_tools.authenticate._verify_user_auth")
    @patch("banking_tools.authenticate._validate_profile")
    @patch.object(constants, "_AUTH_VERIFICATION_DISABLED", True)
    def test_authenticate_with_jwt(
        self, mock_validate, mock_verify, mock_update, mock_list
    ):
        mock_list.return_value = {}
        user_items = {"user_upload_token": "my_jwt"}
        mock_validate.return_value = user_items
        mock_verify.return_value = user_items

        authenticate.authenticate(user_name="testuser", jwt="my_jwt")
        mock_update.assert_called_once()

    @patch("banking_tools.config.list_all_users")
    @patch("banking_tools.config.remove_config")
    def test_authenticate_delete(self, mock_remove, mock_list):
        mock_list.return_value = {"testuser": {"user_upload_token": "tok"}}
        authenticate.authenticate(user_name="testuser", delete=True)
        mock_remove.assert_called_once_with("testuser")

    @patch("banking_tools.config.list_all_users")
    @patch.object(constants, "PROMPT_DISABLED", True)
    def test_authenticate_no_name_no_prompt(self, mock_list):
        mock_list.return_value = {}
        with pytest.raises(exceptions.BankingPlatformBadParameterError):
            authenticate.authenticate()


class TestPromptLogin:
    @patch.object(constants, "PROMPT_DISABLED", True)
    def test_no_email_no_prompt_raises(self):
        with pytest.raises(
            exceptions.BankingPlatformBadParameterError, match="user_email"
        ):
            authenticate._prompt_login()

    @patch.object(constants, "PROMPT_DISABLED", True)
    def test_no_password_no_prompt_raises(self):
        with pytest.raises(
            exceptions.BankingPlatformBadParameterError, match="user_password"
        ):
            authenticate._prompt_login(user_email="test@test.com")

    @patch("banking_tools.api_v4.create_client_session")
    @patch("banking_tools.api_v4.get_upload_token")
    @patch("banking_tools.api_v4.jsonify_response")
    def test_successful_login(self, mock_jsonify, mock_token, mock_session):
        mock_session.return_value.__enter__ = MagicMock()
        mock_session.return_value.__exit__ = MagicMock(return_value=False)
        mock_jsonify.return_value = {"access_token": "newtok", "user_id": "999"}

        result = authenticate._prompt_login(
            user_email="user@test.com", user_password="pass123"
        )
        assert result["user_upload_token"] == "newtok"
        assert result["MAPSettingsUserKey"] == "999"


class TestIsLoginRetryableExtended:
    def test_retryable_subcode(self):
        resp = MagicMock(spec=requests.Response)
        resp.status_code = 400
        resp.json.return_value = {
            "error": {
                "error_subcode": 1348028,
                "error_user_title": "Error",
                "error_user_msg": "msg",
            }
        }
        ex = requests.HTTPError(response=resp)
        assert authenticate._is_login_retryable(ex) is True

    def test_non_retryable_subcode(self):
        resp = MagicMock(spec=requests.Response)
        resp.status_code = 400
        resp.json.return_value = {"error": {"error_subcode": 9999}}
        ex = requests.HTTPError(response=resp)
        assert authenticate._is_login_retryable(ex) is False

    def test_server_error_not_retryable(self):
        resp = MagicMock(spec=requests.Response)
        resp.status_code = 500
        ex = requests.HTTPError(response=resp)
        assert authenticate._is_login_retryable(ex) is False


class TestVerifyUserAuthExtended:
    @patch.object(constants, "_AUTH_VERIFICATION_DISABLED", True)
    def test_disabled_returns_items(self):
        items = {"user_upload_token": "test_token"}
        result = authenticate._verify_user_auth(items)
        assert result == items

    @patch("banking_tools.api_v4.create_user_session")
    @patch("banking_tools.api_v4.fetch_user_or_me")
    @patch("banking_tools.api_v4.jsonify_response")
    @patch.object(constants, "_AUTH_VERIFICATION_DISABLED", False)
    def test_successful_verify(self, mock_jsonify, mock_fetch, mock_session):
        mock_session.return_value.__enter__ = MagicMock()
        mock_session.return_value.__exit__ = MagicMock(return_value=False)
        mock_jsonify.return_value = {"username": "user1", "id": "12345"}
        items = {"user_upload_token": "test_token"}
        result = authenticate._verify_user_auth(items)
        assert result["MAPSettingsUsername"] == "user1"
        assert result["MAPSettingsUserKey"] == "12345"

    @patch("banking_tools.api_v4.create_user_session")
    @patch("banking_tools.api_v4.fetch_user_or_me")
    @patch("banking_tools.api_v4.is_auth_error")
    @patch("banking_tools.api_v4.extract_auth_error_message")
    @patch.object(constants, "_AUTH_VERIFICATION_DISABLED", False)
    def test_auth_error_raises(self, mock_msg, mock_is_auth, mock_fetch, mock_session):
        mock_session.return_value.__enter__ = MagicMock()
        mock_session.return_value.__exit__ = MagicMock(return_value=False)
        resp = MagicMock(spec=requests.Response)
        resp.status_code = 401
        mock_fetch.side_effect = requests.HTTPError(response=resp)
        mock_is_auth.return_value = True
        mock_msg.return_value = "Invalid token"
        items = {"user_upload_token": "bad_token"}
        with pytest.raises(exceptions.BankingPlatformUploadUnauthorizedError):
            authenticate._verify_user_auth(items)


class TestFetchUserItemsExtended:
    @patch("banking_tools.authenticate.config.list_all_users")
    @patch("banking_tools.authenticate._verify_user_auth")
    @patch("banking_tools.authenticate._validate_profile")
    def test_single_profile(self, mock_validate, mock_verify, mock_list):
        mock_list.return_value = {"default": {"user_upload_token": "tok"}}
        mock_validate.return_value = {"user_upload_token": "tok"}
        mock_verify.return_value = {
            "user_upload_token": "tok",
            "MAPSettingsUsername": "user",
            "MAPSettingsUserKey": "123",
        }
        result = authenticate.fetch_user_items()
        assert result["MAPSettingsUserKey"] == "123"

    @patch("banking_tools.authenticate.config.list_all_users")
    @patch("banking_tools.authenticate._verify_user_auth")
    @patch("banking_tools.authenticate._validate_profile")
    def test_named_profile(self, mock_validate, mock_verify, mock_list):
        mock_list.return_value = {
            "profile1": {"user_upload_token": "tok1"},
            "profile2": {"user_upload_token": "tok2"},
        }
        mock_validate.return_value = {"user_upload_token": "tok2"}
        mock_verify.return_value = {
            "user_upload_token": "tok2",
            "MAPSettingsUsername": "u",
            "MAPSettingsUserKey": "456",
        }
        result = authenticate.fetch_user_items(user_name="profile2")
        assert result["MAPSettingsUserKey"] == "456"

    @patch("banking_tools.authenticate.config.list_all_users")
    def test_named_profile_not_found(self, mock_list):
        mock_list.return_value = {"profile1": {"user_upload_token": "tok1"}}
        with pytest.raises(
            exceptions.BankingPlatformBadParameterError, match="not found"
        ):
            authenticate.fetch_user_items(user_name="nonexistent")

    @patch("banking_tools.authenticate.config.list_all_users")
    @patch.object(constants, "PROMPT_DISABLED", True)
    def test_multiple_profiles_no_prompt_raises(self, mock_list):
        mock_list.return_value = {
            "p1": {"user_upload_token": "a"},
            "p2": {"user_upload_token": "b"},
        }
        with pytest.raises(exceptions.BankingPlatformBadParameterError):
            authenticate.fetch_user_items()

    @patch("banking_tools.authenticate.config.list_all_users")
    @patch("banking_tools.authenticate._verify_user_auth")
    @patch("banking_tools.authenticate._validate_profile")
    def test_timeout_raises(self, mock_validate, mock_verify, mock_list):
        mock_list.return_value = {"default": {"user_upload_token": "tok"}}
        mock_validate.return_value = {"user_upload_token": "tok"}
        mock_verify.side_effect = requests.Timeout("timed out")
        with pytest.raises(exceptions.BankingPlatformUploadTimeoutError):
            authenticate.fetch_user_items()

    @patch("banking_tools.authenticate.config.list_all_users")
    @patch("banking_tools.authenticate._verify_user_auth")
    @patch("banking_tools.authenticate._validate_profile")
    def test_connection_error_raises(self, mock_validate, mock_verify, mock_list):
        mock_list.return_value = {"default": {"user_upload_token": "tok"}}
        mock_validate.return_value = {"user_upload_token": "tok"}
        mock_verify.side_effect = requests.ConnectionError("refused")
        with pytest.raises(exceptions.BankingPlatformUploadConnectionError):
            authenticate.fetch_user_items()


class TestValidateProfileExtended:
    def test_valid_profile(self):
        items = {"user_upload_token": "some_token"}
        result = authenticate._validate_profile(items)
        assert result == items

    def test_invalid_profile(self):
        items = {}
        with pytest.raises(
            exceptions.BankingPlatformBadParameterError, match="Invalid profile"
        ):
            authenticate._validate_profile(items)


class TestPromptChooseProfileName:
    @patch.object(authenticate, "_prompt_enabled", return_value=True)
    @patch.object(authenticate, "_prompt")
    def test_select_existing_by_name(self, mock_prompt, _enabled):
        mock_prompt.return_value = "work"
        result = authenticate._prompt_choose_profile_name(["default", "work"])
        assert result == "work"

    @patch.object(authenticate, "_prompt_enabled", return_value=True)
    @patch.object(authenticate, "_prompt")
    def test_select_existing_by_index(self, mock_prompt, _enabled):
        mock_prompt.return_value = "2"
        result = authenticate._prompt_choose_profile_name(["default", "work"])
        assert result == "work"

    @patch.object(authenticate, "_prompt_enabled", return_value=True)
    @patch.object(authenticate, "_prompt")
    def test_empty_then_valid(self, mock_prompt, _enabled):
        mock_prompt.side_effect = ["", "default"]
        result = authenticate._prompt_choose_profile_name(["default"])
        assert result == "default"

    @patch.object(authenticate, "_prompt_enabled", return_value=True)
    @patch.object(authenticate, "_prompt")
    def test_create_new_valid_name(self, mock_prompt, _enabled):
        mock_prompt.return_value = "newprofile"
        result = authenticate._prompt_choose_profile_name([], must_exist=False)
        assert result == "newprofile"

    @patch.object(authenticate, "_prompt_enabled", return_value=True)
    @patch.object(authenticate, "_prompt")
    def test_create_new_invalid_then_valid(self, mock_prompt, _enabled):
        mock_prompt.side_effect = ["1bad", "goodname"]
        result = authenticate._prompt_choose_profile_name([], must_exist=False)
        assert result == "goodname"

    @patch.object(authenticate, "_prompt_enabled", return_value=True)
    @patch.object(authenticate, "_prompt")
    def test_must_exist_not_found_then_found(self, mock_prompt, _enabled):
        mock_prompt.side_effect = ["missing", "default"]
        result = authenticate._prompt_choose_profile_name(["default"], must_exist=True)
        assert result == "default"


class TestPromptLoginRetry:
    @patch.object(constants, "PROMPT_DISABLED", False)
    @patch.object(authenticate, "_prompt_enabled", return_value=True)
    @patch.object(authenticate, "_prompt", return_value="a@b.com")
    @patch("banking_tools.authenticate.getpass.getpass", return_value="pw")
    @patch("banking_tools.api_v4.create_client_session")
    @patch("banking_tools.api_v4.get_upload_token")
    @patch("banking_tools.api_v4.jsonify_response")
    @patch.object(authenticate, "_is_login_retryable")
    def test_retry_then_success(
        self,
        mock_retryable,
        mock_jsonify,
        mock_token,
        mock_session,
        mock_getpass,
        mock_prompt,
        _enabled,
    ):
        mock_session.return_value.__enter__ = MagicMock()
        mock_session.return_value.__exit__ = MagicMock(return_value=False)
        resp = MagicMock(spec=requests.Response)
        resp.status_code = 400
        err = requests.HTTPError(response=resp)
        mock_token.side_effect = [err, MagicMock()]
        mock_retryable.return_value = True
        mock_jsonify.return_value = {"access_token": "tok", "user_id": "1"}

        result = authenticate._prompt_login(user_email="a@b.com", user_password="pw")
        assert result["user_upload_token"] == "tok"

    @patch.object(authenticate, "_prompt_enabled", return_value=True)
    @patch("banking_tools.api_v4.create_client_session")
    @patch("banking_tools.api_v4.get_upload_token")
    @patch.object(authenticate, "_is_login_retryable", return_value=False)
    def test_non_retryable_raises(
        self, mock_retryable, mock_token, mock_session, _enabled
    ):
        mock_session.return_value.__enter__ = MagicMock()
        mock_session.return_value.__exit__ = MagicMock(return_value=False)
        resp = MagicMock(spec=requests.Response)
        resp.status_code = 400
        err = requests.HTTPError(response=resp)
        mock_token.side_effect = err
        with pytest.raises(requests.HTTPError):
            authenticate._prompt_login(user_email="a@b.com", user_password="pw")
