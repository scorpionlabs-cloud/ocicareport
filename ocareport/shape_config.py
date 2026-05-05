# coding: utf-8
"""Shape parsing and sizing helpers."""

from __future__ import annotations

import re
from typing import Iterable, Optional

from ocareport.models import ShapeRequest, ShapeSize


_FIXED_SHAPE_MEMORY_PER_OCPU = {
    # Burstable shapes commonly expose 12 GB per OCPU; e.g. VM.Standard.B1.8 = 96 GB.
    "VM.Standard.B1": 12.0,
    # Legacy/general purpose fallbacks. OCI list_shapes is preferred whenever available.
    "VM.Standard.E2": 8.0,
    "VM.Standard2": 15.0,
    "VM.Standard3": 16.0,
    "VM.Standard.E3": 16.0,
    "VM.Standard.E4": 16.0,
    "VM.Standard.E5": 16.0,
    "VM.Standard.E6": 16.0,
}


def is_flex_shape(shape: str) -> bool:
    """Return True when the shape name appears to be an OCI Flex shape."""
    return "flex" in shape.lower()


def parse_shape_request(value: str, *, default_ocpus: float, default_memory_gb: float) -> ShapeRequest:
    """Parse SHAPE or SHAPE:OCPUS:MEMORY_GB into a ShapeRequest.

    Examples:
        VM.Standard.E5.Flex
        VM.Standard.E5.Flex:8:64
        BM.GPU.H100.8
    """
    parts = value.rsplit(":", 2)
    if len(parts) == 1:
        shape = parts[0].strip()
        if not shape:
            raise ValueError("shape name cannot be empty")
        if is_flex_shape(shape):
            return ShapeRequest(shape, default_ocpus, default_memory_gb)
        return ShapeRequest(shape)

    if len(parts) != 3:
        raise ValueError("shape sizing must use SHAPE:OCPUS:MEMORY_GB")

    shape, raw_ocpus, raw_memory = (part.strip() for part in parts)
    if not shape:
        raise ValueError("shape name cannot be empty")
    try:
        ocpus = float(raw_ocpus)
        memory = float(raw_memory)
    except ValueError as exc:
        raise ValueError("shape sizing must use numeric OCPUS and MEMORY_GB") from exc
    if ocpus <= 0 or memory <= 0:
        raise ValueError("shape sizing values must be greater than 0")
    return ShapeRequest(shape, ocpus, memory)


def dedupe_shape_requests(requests: Iterable[ShapeRequest]) -> list[ShapeRequest]:
    """De-duplicate shape requests while preserving order.

    Size is part of the key so the same flex shape can be checked with multiple configs.
    """
    normalized: list[ShapeRequest] = []
    seen = set()
    for request in requests:
        key = (request.name.lower(), request.ocpus, request.memory_gb)
        if key not in seen:
            normalized.append(request)
            seen.add(key)
    return normalized


def infer_fixed_shape_size(shape: str) -> ShapeSize:
    """Best-effort sizing for fixed shapes when OCI list_shapes is unavailable.

    The Compute list_shapes API is the source of truth. This function only prevents
    known fixed shapes from displaying the flex defaults when shape metadata cannot
    be resolved.
    """
    match = re.search(r"\.(\d+)$", shape)
    if not match:
        return ShapeSize(None, None)

    ocpus = float(match.group(1))
    for prefix, memory_per_ocpu in sorted(
        _FIXED_SHAPE_MEMORY_PER_OCPU.items(), key=lambda item: len(item[0]), reverse=True
    ):
        if shape.startswith(prefix):
            return ShapeSize(ocpus, ocpus * memory_per_ocpu)
    return ShapeSize(ocpus, None)


def extract_oci_shape_size(shape_obj) -> ShapeSize:
    """Extract OCPU and memory values from an OCI Shape object."""
    ocpus = getattr(shape_obj, "ocpus", None)
    memory = getattr(shape_obj, "memory_in_gbs", None)
    return ShapeSize(ocpus, memory)


def effective_shape_size(request: ShapeRequest, resolved: Optional[ShapeSize] = None) -> ShapeSize:
    """Return the best display size for a shape request.

    For flex shapes, the requested shape config is authoritative. For fixed shapes,
    OCI list_shapes metadata is preferred; otherwise, use a best-effort inference.
    """
    if request.ocpus is not None or request.memory_gb is not None:
        return ShapeSize(request.ocpus, request.memory_gb)
    if resolved and (resolved.ocpus is not None or resolved.memory_gb is not None):
        return resolved
    return infer_fixed_shape_size(request.name)
