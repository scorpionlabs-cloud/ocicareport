"""Test OCI SDK stub used when the real oci package is unavailable."""

from __future__ import annotations

import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


if "oci" not in sys.modules:
    oci = types.ModuleType("oci")

    class ServiceError(Exception):
        def __init__(self, message="service error"):
            super().__init__(message)
            self.message = message

    class _RetryStrategyBuilder:
        def __init__(self, **_kwargs):
            pass

        def get_retry_strategy(self):
            return object()

    class _Config:
        @staticmethod
        def from_file(*_args, **_kwargs):
            return {}

        @staticmethod
        def validate_config(_config):
            return None

        @staticmethod
        def get_config_value_or_default(config, key):
            return config.get(key)

    class _Signer:
        def __init__(self, **_kwargs):
            pass

    class _IPSigner:
        def __init__(self, **_kwargs):
            self.region = "us-ashburn-1"
            self.tenancy_id = "test-tenancy-id"

    class _DelegationTokenSigner:
        def __init__(self, **_kwargs):
            pass

    class _IdentityClient:
        def __init__(self, *args, **kwargs):
            pass

    class _ComputeClient:
        def __init__(self, *args, **kwargs):
            pass

    class _CapacityReportInstanceShapeConfig:
        def __init__(self, ocpus=None, memory_in_gbs=None):
            self.ocpus = ocpus
            self.memory_in_gbs = memory_in_gbs

    class _CreateCapacityReportShapeAvailabilityDetails:
        def __init__(self, instance_shape=None, fault_domain=None, instance_shape_config=None):
            self.instance_shape = instance_shape
            self.fault_domain = fault_domain
            self.instance_shape_config = instance_shape_config

    class _CreateComputeCapacityReportDetails:
        def __init__(self, compartment_id=None, availability_domain=None, shape_availabilities=None):
            self.compartment_id = compartment_id
            self.availability_domain = availability_domain
            self.shape_availabilities = shape_availabilities or []

    def _list_call_get_all_results(func, *args, **kwargs):
        return func(*args, **kwargs)

    oci.exceptions = types.SimpleNamespace(ServiceError=ServiceError)
    oci.retry = types.SimpleNamespace(RetryStrategyBuilder=_RetryStrategyBuilder)
    oci.config = _Config
    oci.signer = types.SimpleNamespace(Signer=_Signer)
    oci.auth = types.SimpleNamespace(
        signers=types.SimpleNamespace(
            InstancePrincipalsSecurityTokenSigner=_IPSigner,
            InstancePrincipalsDelegationTokenSigner=_DelegationTokenSigner,
        )
    )
    oci.identity = types.SimpleNamespace(IdentityClient=_IdentityClient)
    oci.pagination = types.SimpleNamespace(list_call_get_all_results=_list_call_get_all_results)
    oci.core = types.SimpleNamespace(
        ComputeClient=_ComputeClient,
        models=types.SimpleNamespace(
            CapacityReportInstanceShapeConfig=_CapacityReportInstanceShapeConfig,
            CreateCapacityReportShapeAvailabilityDetails=_CreateCapacityReportShapeAvailabilityDetails,
            CreateComputeCapacityReportDetails=_CreateComputeCapacityReportDetails,
        ),
    )

    sys.modules["oci"] = oci
