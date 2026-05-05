# coding: utf-8
"""Typed data structures for OCI capacity checks."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class ShapeRequest:
    """One requested compute shape and its optional explicit resource sizing."""

    name: str
    ocpus: Optional[float] = None
    memory_gb: Optional[float] = None

    @property
    def is_sized(self) -> bool:
        """Return True when both OCPU and memory were explicitly supplied."""
        return self.ocpus is not None and self.memory_gb is not None


@dataclass(frozen=True)
class ShapeSize:
    """Effective OCPU and memory values displayed for a shape result."""

    ocpus: Optional[float]
    memory_gb: Optional[float]


@dataclass(frozen=True)
class CapacityResult:
    """One capacity report result or recoverable scan error.

    ocpus and memory_gb represent total available resources for the row target
    when OCI returns available_count. If OCI suppresses available_count but the
    status is AVAILABLE, they represent the exact requested/per-instance shape
    configuration that OCI confirmed can be created. instance_ocpus and
    instance_memory_gb retain that requested/per-instance shape size for
    machine-readable output.
    """

    region: str
    availability_domain: str
    fault_domain: str
    shape: str
    ocpus: Optional[float]
    memory_gb: Optional[float]
    status: str
    error: Optional[str] = None
    available_count: Optional[int] = None
    instance_ocpus: Optional[float] = None
    instance_memory_gb: Optional[float] = None

    @property
    def ok(self) -> bool:
        """Return True when this row is a successful API result."""
        return self.error is None

    def to_dict(self) -> dict:
        """Return a machine-friendly dictionary representation.

        available_count is intentionally not exposed in JSON/CSV output. It is
        used internally to derive total OCPU and memory when OCI provides it,
        but the public output keeps capacity focused on OCPU and memory.
        """
        return {
            "region": self.region,
            "availability_domain": self.availability_domain,
            "fault_domain": self.fault_domain,
            "shape": self.shape,
            "ocpus": self.ocpus,
            "memory_gb": self.memory_gb,
            "instance_ocpus": self.instance_ocpus,
            "instance_memory_gb": self.instance_memory_gb,
            "status": self.status,
            "error": self.error,
        }
