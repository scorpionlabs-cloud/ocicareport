# coding: utf-8
"""OCI Compute Capacity Report API helpers and scan orchestration."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Iterable, List

import oci

from ocareport.identity import get_availability_domains, get_fault_domains
from ocareport.models import CapacityResult, ShapeRequest, ShapeSize
from ocareport.shape_config import effective_shape_size, extract_oci_shape_size, is_flex_shape


def create_capacity_report(
    core_client,
    compartment_id,
    availability_domain,
    fault_domain,
    shape,
    is_flex=False,
    ocpu=1.0,
    memory=1.0,
):
    """Query the Compute Capacity Report API for one shape target.

    Returns the first CapacityReportShapeAvailability object. It includes the
    availability_status, available_count, and returned instance_shape_config
    fields that are needed to derive total available OCPU and memory.
    """
    shape_config = None
    if is_flex:
        shape_config = oci.core.models.CapacityReportInstanceShapeConfig(
            ocpus=ocpu,
            memory_in_gbs=memory,
        )

    report_details = oci.core.models.CreateComputeCapacityReportDetails(
        compartment_id=compartment_id,
        availability_domain=availability_domain,
        shape_availabilities=[
            oci.core.models.CreateCapacityReportShapeAvailabilityDetails(
                instance_shape=shape,
                fault_domain=fault_domain,
                instance_shape_config=shape_config,
            )
        ],
    )

    report = core_client.create_compute_capacity_report(
        create_compute_capacity_report_details=report_details,
    )

    return report.data.shape_availabilities[0]


def _number_or_none(value):
    """Convert SDK numeric-ish values to float, preserving None."""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _integer_or_none(value):
    """Convert SDK integer-ish values to int, preserving None."""
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _shape_config_size(shape_availability, fallback_size: ShapeSize) -> ShapeSize:
    """Return the per-instance shape size from the report or fallback metadata."""
    config = getattr(shape_availability, "instance_shape_config", None)
    ocpus = _number_or_none(getattr(config, "ocpus", None))
    memory = _number_or_none(getattr(config, "memory_in_gbs", None))
    return ShapeSize(
        ocpus if ocpus is not None else fallback_size.ocpus,
        memory if memory is not None else fallback_size.memory_gb,
    )


def _capacity_values(shape_availability, instance_size: ShapeSize) -> tuple[int | None, ShapeSize]:
    """Return available count and numeric capacity values.

    OCI returns available_count only when the service exposes the precise count
    to the tenancy. When status is AVAILABLE but available_count is omitted,
    show the exact requested/per-instance capacity that OCI confirmed can be
    created instead of using a symbolic lower-bound marker.
    """
    status = getattr(shape_availability, "availability_status", None)
    available_count = _integer_or_none(getattr(shape_availability, "available_count", None))

    if available_count is None:
        available_count = 1 if status == "AVAILABLE" else 0

    total_ocpus = (instance_size.ocpus * available_count) if instance_size.ocpus is not None else None
    total_memory = (instance_size.memory_gb * available_count) if instance_size.memory_gb is not None else None
    return available_count, ShapeSize(total_ocpus, total_memory)


def _service_error_message(exc: Exception) -> str:
    """Return a concise OCI ServiceError message."""
    return getattr(exc, "message", str(exc))


def _scan_fault_domain(
    *,
    config: dict,
    signer,
    tenancy_id: str,
    region_name: str,
    availability_domain: str,
    fault_domain: str,
    request: ShapeRequest,
    display_size: ShapeSize,
) -> CapacityResult:
    """Scan one region/AD/FD/shape tuple and convert failures into result rows."""
    region_config = dict(config)
    region_config["region"] = region_name
    core_client = oci.core.ComputeClient(config=region_config, signer=signer)

    is_flex = is_flex_shape(request.name)
    request_ocpus = request.ocpus if request.ocpus is not None else 1.0
    request_memory = request.memory_gb if request.memory_gb is not None else 1.0

    try:
        shape_availability = create_capacity_report(
            core_client,
            tenancy_id,
            availability_domain,
            fault_domain,
            request.name,
            is_flex,
            request_ocpus,
            request_memory,
        )
        instance_size = _shape_config_size(shape_availability, display_size)
        available_count, total_size = _capacity_values(shape_availability, instance_size)
        return CapacityResult(
            region=region_name,
            availability_domain=availability_domain,
            fault_domain=fault_domain,
            shape=request.name,
            ocpus=total_size.ocpus,
            memory_gb=total_size.memory_gb,
            status=getattr(shape_availability, "availability_status", "UNKNOWN"),
            available_count=available_count,
            instance_ocpus=instance_size.ocpus,
            instance_memory_gb=instance_size.memory_gb,
        )
    except oci.exceptions.ServiceError as exc:
        return CapacityResult(
            region=region_name,
            availability_domain=availability_domain,
            fault_domain=fault_domain,
            shape=request.name,
            ocpus=None,
            memory_gb=None,
            status="ERROR",
            error=_service_error_message(exc),
            instance_ocpus=display_size.ocpus,
            instance_memory_gb=display_size.memory_gb,
        )


def build_scan_targets(config: dict, signer, tenancy_id: str, regions: Iterable) -> List[tuple[str, str, str]]:
    """Build all region/availability-domain/fault-domain tuples to scan.

    Region metadata failures are represented as synthetic ERROR targets by the caller;
    this function raises OCI ServiceError for unrecoverable metadata calls so the CLI
    can decide whether to stop or continue.
    """
    targets: List[tuple[str, str, str]] = []
    for region in regions:
        region_name = region.region_name
        region_config = dict(config)
        region_config["region"] = region_name
        identity_client = oci.identity.IdentityClient(config=region_config, signer=signer)
        ads = get_availability_domains(identity_client, tenancy_id)
        for ad in ads:
            fds = get_fault_domains(identity_client, tenancy_id, ad)
            for fd in fds:
                targets.append((region_name, ad, fd))
    return targets


def resolve_shape_sizes(
    *,
    config: dict,
    signer,
    tenancy_id: str,
    targets: Iterable[tuple[str, str, str]],
    shape_requests: Iterable[ShapeRequest],
) -> dict[tuple[str, str, ShapeRequest], ShapeSize]:
    """Resolve accurate fixed-shape OCPU/memory values through OCI list_shapes.

    Flex shapes use the requested shape config. Fixed shapes prefer OCI shape metadata
    by region and availability domain. If metadata lookup is unavailable, a best-effort
    fixed-shape inference is used instead of showing misleading flex defaults.
    """
    requests = list(shape_requests)
    unique_region_ads = sorted({(region, ad) for region, ad, _fd in targets})
    size_map: dict[tuple[str, str, ShapeRequest], ShapeSize] = {}

    for region_name, availability_domain in unique_region_ads:
        resolved_by_shape: dict[str, ShapeSize] = {}
        region_config = dict(config)
        region_config["region"] = region_name
        try:
            core_client = oci.core.ComputeClient(config=region_config, signer=signer)
            response = core_client.list_shapes(
                compartment_id=tenancy_id,
                availability_domain=availability_domain,
            )
            for shape_obj in response.data:
                shape_name = getattr(shape_obj, "shape", None)
                if shape_name:
                    resolved_by_shape[shape_name] = extract_oci_shape_size(shape_obj)
        except (oci.exceptions.ServiceError, AttributeError):
            resolved_by_shape = {}

        for request in requests:
            size_map[(region_name, availability_domain, request)] = effective_shape_size(
                request,
                resolved_by_shape.get(request.name),
            )

    return size_map


def scan_capacity(
    *,
    config: dict,
    signer,
    tenancy_id: str,
    targets: Iterable[tuple[str, str, str]],
    shapes: Iterable[str] | None = None,
    shape_requests: Iterable[ShapeRequest] | None = None,
    ocpu: float = 1.0,
    memory: float = 1.0,
    workers: int = 1,
) -> List[CapacityResult]:
    """Scan every requested shape across every target, using bounded concurrency."""
    target_list = list(targets)
    if shape_requests is None:
        shape_requests = [
            ShapeRequest(shape, ocpu, memory) if is_flex_shape(shape) else ShapeRequest(shape)
            for shape in list(shapes or [])
        ]
    request_list = list(shape_requests)
    size_map = resolve_shape_sizes(
        config=config,
        signer=signer,
        tenancy_id=tenancy_id,
        targets=target_list,
        shape_requests=request_list,
    )
    target_shape_pairs = [
        (region_name, ad, fd, request)
        for region_name, ad, fd in target_list
        for request in request_list
    ]

    if workers <= 1:
        return [
            _scan_fault_domain(
                config=config,
                signer=signer,
                tenancy_id=tenancy_id,
                region_name=region_name,
                availability_domain=ad,
                fault_domain=fd,
                request=request,
                display_size=size_map[(region_name, ad, request)],
            )
            for region_name, ad, fd, request in target_shape_pairs
        ]

    results: List[CapacityResult] = []
    max_workers = min(workers, max(len(target_shape_pairs), 1))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_map = {
            executor.submit(
                _scan_fault_domain,
                config=config,
                signer=signer,
                tenancy_id=tenancy_id,
                region_name=region_name,
                availability_domain=ad,
                fault_domain=fd,
                request=request,
                display_size=size_map[(region_name, ad, request)],
            ): (region_name, ad, fd, request.name)
            for region_name, ad, fd, request in target_shape_pairs
        }
        for future in as_completed(future_map):
            results.append(future.result())

    return sorted(
        results,
        key=lambda r: (r.region, r.availability_domain, r.fault_domain, r.shape, r.ocpus or 0, r.memory_gb or 0),
    )
