# coding: utf-8
"""Output renderers for capacity scan results."""

from __future__ import annotations

import csv
import json
import sys
from collections import Counter
from typing import Iterable, TextIO

from rich import box
from rich.console import Console
from rich.table import Table

from ocareport.models import CapacityResult


FIELDNAMES = [
    "region",
    "availability_domain",
    "fault_domain",
    "shape",
    "ocpus",
    "memory_gb",
    "instance_ocpus",
    "instance_memory_gb",
    "status",
    "error",
]


def render_table(results: Iterable[CapacityResult], *, shapes: list[str], ocpu: float, memory: float) -> None:
    """Render results as a Rich table."""
    console = Console()
    shape_label = ", ".join(shapes)
    table = Table(
        title=f"Shapes: {shape_label}",
        box=box.MARKDOWN,
    )
    table.add_column("REGION", justify="left")
    table.add_column("AVAILABILITY DOMAIN", justify="left")
    table.add_column("FAULT DOMAIN", justify="left")
    table.add_column("SHAPE", justify="left")
    table.add_column("OCPU", justify="right")
    table.add_column("MEMORY", justify="right")
    table.add_column("STATUS", justify="left")
    table.add_column("ERROR", justify="left")

    for result in results:
        style = "green" if result.status == "AVAILABLE" else "red" if result.status == "ERROR" else None
        table.add_row(
            result.region,
            result.availability_domain,
            result.fault_domain,
            result.shape,
            _format_number(result.ocpus),
            _format_number(result.memory_gb),
            result.status,
            result.error or "",
            style=style,
        )

    console.print(table)
    console.print(
        "[dim]OCPU and MEMORY show total available capacity when OCI exposes an exact count; "
        "otherwise they show the numeric requested capacity that OCI confirmed is available.[/dim]"
    )


def _format_number(value) -> str:
    """Format an optional numeric value for compact table display."""
    if value is None:
        return ""
    return f"{value:g}"


def render_json(results: Iterable[CapacityResult], stream: TextIO = sys.stdout) -> None:
    """Render results as pretty JSON."""
    json.dump([result.to_dict() for result in results], stream, indent=2)
    stream.write("\n")


def render_csv(results: Iterable[CapacityResult], stream: TextIO = sys.stdout) -> None:
    """Render results as CSV."""
    writer = csv.DictWriter(stream, fieldnames=FIELDNAMES)
    writer.writeheader()
    for result in results:
        writer.writerow(result.to_dict())


def render_results(results: list[CapacityResult], *, output: str, shapes: list[str], ocpu: float, memory: float) -> None:
    """Render results in the requested output format."""
    if output == "json":
        render_json(results)
    elif output == "csv":
        render_csv(results)
    else:
        render_table(results, shapes=shapes, ocpu=ocpu, memory=memory)
        render_summary(results)


def render_summary(results: Iterable[CapacityResult]) -> None:
    """Render a compact human-readable summary."""
    result_list = list(results)
    counts = Counter(result.status for result in result_list)
    errors = sum(1 for result in result_list if result.error)
    Console().print(
        f"[bold]Summary:[/bold] checked={len(result_list)} "
        f"available={counts.get('AVAILABLE', 0)} "
        f"errors={errors}"
    )
