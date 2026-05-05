from __future__ import annotations

from unittest import mock

import pytest

from ocareport import identity


class TestGetAvailabilityDomains:
    def test_returns_ad_names(self):
        mock_client = mock.MagicMock()
        mock_ad1 = mock.MagicMock()
        mock_ad1.name = "AD-1"
        mock_ad2 = mock.MagicMock()
        mock_ad2.name = "AD-2"
        response = mock.MagicMock(data=[mock_ad1, mock_ad2])

        with mock.patch("ocareport.identity.oci.pagination.list_call_get_all_results", return_value=response):
            result = identity.get_availability_domains(mock_client, "test-compartment")

        assert result == ["AD-1", "AD-2"]


class TestGetFaultDomains:
    def test_returns_fd_names(self):
        mock_client = mock.MagicMock()
        mock_fd1 = mock.MagicMock()
        mock_fd1.name = "FD-1"
        mock_fd2 = mock.MagicMock()
        mock_fd2.name = "FD-2"
        response = mock.MagicMock(data=[mock_fd1, mock_fd2])

        with mock.patch("ocareport.identity.oci.pagination.list_call_get_all_results", return_value=response):
            result = identity.get_fault_domains(mock_client, "test-compartment", "AD-1")

        assert result == ["FD-1", "FD-2"]


class TestGetRegionSubscriptionList:
    def test_returns_all_regions(self):
        mock_client = mock.MagicMock()
        mock_region1 = mock.MagicMock()
        mock_region1.region_name = "us-ashburn-1"
        mock_region1.is_home_region = True
        mock_region2 = mock.MagicMock()
        mock_region2.region_name = "eu-frankfurt-1"
        mock_region2.is_home_region = False
        mock_client.list_region_subscriptions.return_value.data = [mock_region1, mock_region2]

        result = identity.get_region_subscription_list(mock_client, "test-tenancy", "all")

        assert len(result) == 2


class TestAuthentication:
    def test_forced_auth_failure_exits_without_retry_prompt(self):
        def fail_config_auth(auth_errors, *_args):
            auth_errors["Config_File"] = "config failed"
            return None, None, None, None, None, None

        with mock.patch("ocareport.identity.authenticate_config_file", side_effect=fail_config_auth):
            with mock.patch("ocareport.identity.retry_auth") as mock_retry:
                with mock.patch("ocareport.identity.print_error") as mock_print_error:
                    with pytest.raises(SystemExit) as exc_info:
                        identity.init_authentication("cf", "~/.oci/config", "DEFAULT")

        assert exc_info.value.code == 1
        mock_retry.assert_not_called()
        mock_print_error.assert_called_once_with("Config_File", "config failed")
