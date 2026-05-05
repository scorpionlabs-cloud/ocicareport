from __future__ import annotations

from unittest import mock

import pytest

from ocareport import cli


class TestArgumentParsing:
    def test_shape_argument_is_required(self):
        with pytest.raises(SystemExit):
            cli.parse_arguments([])

    def test_default_values(self):
        args = cli.parse_arguments(["-shape", "TestShape"])
        assert args.auth_method == ""
        assert args.config_file_path == "~/.oci/config"
        assert args.config_profile == "DEFAULT"
        assert args.region == ""
        assert args.regions == []
        assert args.shape == "TestShape"
        assert args.shapes == ["TestShape"]
        assert args.ocpu == 1.0
        assert args.memory == 1.0
        assert args.output == "table"
        assert args.workers == 1
        assert args.fail_fast is False

    def test_json_csv_output_options(self):
        assert cli.parse_arguments(["-shape", "TestShape", "--output", "json"]).output == "json"
        assert cli.parse_arguments(["-shape", "TestShape", "--output", "csv"]).output == "csv"

    def test_multiple_shapes_support_repeated_and_comma_values(self):
        args = cli.parse_arguments([
            "-shape",
            "VM.Standard.E5.Flex,BM.GPU.H100.8",
            "-shape",
            "VM.Standard3.Flex",
        ])
        assert args.shapes == ["VM.Standard.E5.Flex", "BM.GPU.H100.8", "VM.Standard3.Flex"]
        assert args.shape == "VM.Standard.E5.Flex,BM.GPU.H100.8,VM.Standard3.Flex"

    def test_multiple_regions_support_repeated_and_comma_values(self):
        args = cli.parse_arguments([
            "-shape",
            "TestShape",
            "-region",
            "us-ashburn-1,eu-frankfurt-1",
            "-region",
            "ap-singapore-1",
        ])
        assert args.regions == ["us-ashburn-1", "eu-frankfurt-1", "ap-singapore-1"]
        assert args.region == "us-ashburn-1,eu-frankfurt-1,ap-singapore-1"

    def test_workers_must_be_positive(self):
        with pytest.raises(SystemExit):
            cli.parse_arguments(["-shape", "TestShape", "--workers", "0"])

    @pytest.mark.parametrize("option", ["-ocpus", "-memory"])
    @pytest.mark.parametrize("value", ["0", "-1"])
    def test_flex_resource_options_must_be_positive(self, option, value):
        with pytest.raises(SystemExit):
            cli.parse_arguments(["-shape", "TestShape", option, value])


class TestMain:
    def test_main_function_exists(self):
        assert callable(cli.main)

    def test_main_returns_partial_failure_code_for_error_rows(self):
        region = mock.MagicMock(region_name="us-ashburn-1")
        tenancy = mock.MagicMock(name="test-tenancy", home_region_key="IAD")

        with mock.patch("ocareport.cli.init_authentication") as mock_auth:
            with mock.patch("ocareport.cli.oci.identity.IdentityClient"):
                with mock.patch("ocareport.cli.get_region_subscription_list", return_value=[region]):
                    with mock.patch("ocareport.cli.build_scan_targets", return_value=[("us-ashburn-1", "AD-1", "FD-1")]):
                        with mock.patch("ocareport.cli.scan_capacity") as mock_scan:
                            with mock.patch("ocareport.cli.render_results"):
                                from ocareport.models import CapacityResult

                                mock_auth.return_value = ({}, None, tenancy, "config_file", "DEFAULT", "tenancy")
                                mock_scan.return_value = [
                                    CapacityResult(
                                        region="us-ashburn-1",
                                        availability_domain="AD-1",
                                        fault_domain="FD-1",
                                        shape="TestShape",
                                        ocpus=1.0,
                                        memory_gb=1.0,
                                        status="ERROR",
                                        error="boom",
                                    )
                                ]
                                code = cli.main(["-shape", "TestShape", "--output", "json"])

        assert code == 5


def test_flex_shape_can_supply_per_shape_resources():
    args = cli.parse_arguments([
        "-shape",
        "VM.Standard.E5.Flex:8:64,VM.Standard.E4.Flex:4:32",
    ])
    assert args.shapes == ["VM.Standard.E5.Flex", "VM.Standard.E4.Flex"]
    assert args.shape_requests[0].ocpus == 8.0
    assert args.shape_requests[0].memory_gb == 64.0
    assert args.shape_requests[1].ocpus == 4.0
    assert args.shape_requests[1].memory_gb == 32.0


def test_invalid_per_shape_resources_exit():
    with pytest.raises(SystemExit):
        cli.parse_arguments(["-shape", "VM.Standard.E5.Flex:bad:64"])
