from __future__ import annotations

from unittest import mock

from ocareport.capacity import create_capacity_report, is_flex_shape, scan_capacity


class TestFlexShapeDetection:
    def test_flex_detected_in_shape_name(self):
        assert is_flex_shape("VM.Standard.E5.Flex")
        assert is_flex_shape("vm.optimized3.flex")

    def test_non_flex_shape(self):
        assert not is_flex_shape("VM.Standard2.1")
        assert not is_flex_shape("BM.Standard.E4.128")


class TestCreateCapacityReport:
    def test_available_shape(self):
        mock_client = mock.MagicMock()
        mock_result = mock.MagicMock()
        mock_result.availability_status = "AVAILABLE"
        mock_client.create_compute_capacity_report.return_value.data.shape_availabilities = [mock_result]

        availability = create_capacity_report(mock_client, "compartment-id", "AD-1", "FD-1", "TestShape")

        assert availability.availability_status == "AVAILABLE"

    def test_flex_shape_config_passed(self):
        mock_client = mock.MagicMock()
        mock_result = mock.MagicMock(availability_status="AVAILABLE")
        mock_client.create_compute_capacity_report.return_value.data.shape_availabilities = [mock_result]

        create_capacity_report(
            mock_client,
            "compartment-id",
            "AD-1",
            "FD-1",
            "VM.Standard.E5.Flex",
            is_flex=True,
            ocpu=24.0,
            memory=512.0,
        )

        report_details = mock_client.create_compute_capacity_report.call_args[1][
            "create_compute_capacity_report_details"
        ]
        shape_config = report_details.shape_availabilities[0].instance_shape_config
        assert shape_config.ocpus == 24.0
        assert shape_config.memory_in_gbs == 512.0


class TestScanCapacity:
    def test_scan_capacity_uses_threaded_path(self):
        targets = [("us-ashburn-1", "AD-1", "FD-1"), ("us-ashburn-1", "AD-1", "FD-2")]
        with mock.patch("ocareport.capacity._scan_fault_domain") as scan_one:
            from ocareport.models import CapacityResult

            scan_one.side_effect = [
                CapacityResult("us-ashburn-1", "AD-1", "FD-1", "TestShape", 1.0, 1.0, "AVAILABLE"),
                CapacityResult("us-ashburn-1", "AD-1", "FD-2", "TestShape", 1.0, 1.0, "OUT_OF_HOST_CAPACITY"),
            ]
            results = scan_capacity(
                config={},
                signer=None,
                tenancy_id="tenancy",
                targets=targets,
                shapes=["TestShape"],
                ocpu=1.0,
                memory=1.0,
                workers=2,
            )

        assert len(results) == 2

    def test_scan_capacity_checks_each_shape_for_each_target(self):
        targets = [("us-ashburn-1", "AD-1", "FD-1")]
        with mock.patch("ocareport.capacity._scan_fault_domain") as scan_one:
            from ocareport.models import CapacityResult

            scan_one.side_effect = [
                CapacityResult("us-ashburn-1", "AD-1", "FD-1", "ShapeA", 1.0, 1.0, "AVAILABLE"),
                CapacityResult("us-ashburn-1", "AD-1", "FD-1", "ShapeB", 1.0, 1.0, "OUT_OF_HOST_CAPACITY"),
            ]
            results = scan_capacity(
                config={},
                signer=None,
                tenancy_id="tenancy",
                targets=targets,
                shapes=["ShapeA", "ShapeB"],
                ocpu=1.0,
                memory=1.0,
                workers=1,
            )

        assert [result.shape for result in results] == ["ShapeA", "ShapeB"]
        assert scan_one.call_count == 2


class TestShapeSizing:
    def test_fixed_shape_size_falls_back_to_known_inference(self):
        from ocareport.shape_config import infer_fixed_shape_size

        size = infer_fixed_shape_size("VM.Standard.B1.8")
        assert size.ocpus == 8.0
        assert size.memory_gb == 96.0

    def test_resolve_shape_sizes_uses_oci_list_shapes_metadata(self):
        from ocareport.capacity import resolve_shape_sizes
        from ocareport.models import ShapeRequest

        shape_obj = mock.MagicMock()
        shape_obj.shape = "VM.Standard.Custom.7"
        shape_obj.ocpus = 7.0
        shape_obj.memory_in_gbs = 77.0
        mock_client = mock.MagicMock()
        mock_client.list_shapes.return_value.data = [shape_obj]

        with mock.patch("ocareport.capacity.oci.core.ComputeClient", return_value=mock_client):
            sizes = resolve_shape_sizes(
                config={},
                signer=None,
                tenancy_id="tenancy",
                targets=[("us-ashburn-1", "AD-1", "FD-1")],
                shape_requests=[ShapeRequest("VM.Standard.Custom.7")],
            )

        size = next(iter(sizes.values()))
        assert size.ocpus == 7.0
        assert size.memory_gb == 77.0

    def test_flex_shape_uses_requested_size(self):
        from ocareport.models import ShapeRequest
        from ocareport.shape_config import effective_shape_size

        size = effective_shape_size(ShapeRequest("VM.Standard.E5.Flex", 12.0, 192.0))
        assert size.ocpus == 12.0
        assert size.memory_gb == 192.0

    def test_scan_fault_domain_derives_total_available_resources(self):
        from ocareport.capacity import _scan_fault_domain
        from ocareport.models import ShapeRequest, ShapeSize

        shape_config = mock.MagicMock()
        shape_config.ocpus = 8.0
        shape_config.memory_in_gbs = 96.0
        availability = mock.MagicMock()
        availability.availability_status = "AVAILABLE"
        availability.available_count = 3
        availability.instance_shape_config = shape_config

        with mock.patch("ocareport.capacity.create_capacity_report", return_value=availability):
            result = _scan_fault_domain(
                config={},
                signer=None,
                tenancy_id="tenancy",
                region_name="eu-frankfurt-1",
                availability_domain="AD-1",
                fault_domain="FAULT-DOMAIN-1",
                request=ShapeRequest("VM.Standard.B1.8"),
                display_size=ShapeSize(8.0, 96.0),
            )

        assert result.available_count == 3
        assert result.instance_ocpus == 8.0
        assert result.instance_memory_gb == 96.0
        assert result.ocpus == 24.0
        assert result.memory_gb == 288.0
    def test_scan_fault_domain_uses_numeric_requested_capacity_when_available_count_is_missing(self):
        from ocareport.capacity import _scan_fault_domain
        from ocareport.models import ShapeRequest, ShapeSize

        shape_config = mock.MagicMock()
        shape_config.ocpus = 8.0
        shape_config.memory_in_gbs = 96.0
        availability = mock.MagicMock()
        availability.availability_status = "AVAILABLE"
        availability.available_count = None
        availability.instance_shape_config = shape_config

        with mock.patch("ocareport.capacity.create_capacity_report", return_value=availability):
            result = _scan_fault_domain(
                config={},
                signer=None,
                tenancy_id="tenancy",
                region_name="eu-frankfurt-1",
                availability_domain="AD-1",
                fault_domain="FAULT-DOMAIN-1",
                request=ShapeRequest("VM.Standard.B1.8"),
                display_size=ShapeSize(8.0, 96.0),
            )

        assert result.available_count == 1
        assert result.ocpus == 8.0
        assert result.memory_gb == 96.0

