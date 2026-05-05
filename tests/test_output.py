from __future__ import annotations

import csv
import io
import json

from ocareport.models import CapacityResult
from ocareport.output import render_csv, render_json, render_table


def test_table_output_includes_total_ocpu_memory_without_count_column(capsys):
    render_table(
        [
            CapacityResult(
                region="eu-frankfurt-1",
                availability_domain="fyxu:EU-FRANKFURT-1-AD-1",
                fault_domain="FAULT-DOMAIN-1",
                shape="VM.Standard.B1.8",
                ocpus=24.0,
                memory_gb=288.0,
                status="AVAILABLE",
                available_count=3,
                instance_ocpus=8.0,
                instance_memory_gb=96.0,
            )
        ],
        shapes=["VM.Standard.B1.8"],
        ocpu=8.0,
        memory=96.0,
    )
    output = capsys.readouterr().out
    assert "COUNT" not in output
    assert "OCPU" in output
    assert "MEMORY" in output
    assert "24" in output
    assert "288" in output


def test_json_output_includes_capacity_fields_without_available_count():
    stream = io.StringIO()
    render_json(
        [
            CapacityResult(
                "eu-frankfurt-1",
                "AD-1",
                "FD-1",
                "VM.Standard.B1.8",
                24.0,
                288.0,
                "AVAILABLE",
                available_count=3,
                instance_ocpus=8.0,
                instance_memory_gb=96.0,
            )
        ],
        stream=stream,
    )
    data = json.loads(stream.getvalue())
    assert "available_count" not in data[0]
    assert "available_count_is_lower_bound" not in data[0]
    assert "capacity_is_lower_bound" not in data[0]
    assert data[0]["ocpus"] == 24.0
    assert data[0]["memory_gb"] == 288.0
    assert data[0]["instance_ocpus"] == 8.0
    assert data[0]["instance_memory_gb"] == 96.0


def test_csv_output_includes_capacity_fields_without_available_count():
    stream = io.StringIO()
    render_csv(
        [
            CapacityResult(
                "eu-frankfurt-1",
                "AD-1",
                "FD-1",
                "VM.Standard.B1.8",
                24.0,
                288.0,
                "AVAILABLE",
                available_count=3,
                instance_ocpus=8.0,
                instance_memory_gb=96.0,
            )
        ],
        stream=stream,
    )
    row = next(csv.DictReader(io.StringIO(stream.getvalue())))
    assert "available_count" not in row
    assert "available_count_is_lower_bound" not in row
    assert "capacity_is_lower_bound" not in row
    assert row["ocpus"] == "24.0"
    assert row["memory_gb"] == "288.0"
    assert row["instance_ocpus"] == "8.0"
    assert row["instance_memory_gb"] == "96.0"


def test_table_output_uses_plain_numbers_when_available_count_is_missing(capsys):
    render_table(
        [
            CapacityResult(
                region="ap-singapore-1",
                availability_domain="AD-1",
                fault_domain="FAULT-DOMAIN-1",
                shape="VM.Standard.E5.Flex",
                ocpus=1.0,
                memory_gb=1.0,
                status="AVAILABLE",
                available_count=1,
                instance_ocpus=1.0,
                instance_memory_gb=1.0,
            )
        ],
        shapes=["VM.Standard.E5.Flex"],
        ocpu=1.0,
        memory=1.0,
    )
    output = capsys.readouterr().out
    assert ">=1" not in output
    assert "lower bounds" not in output
    assert " 1 " in output or "│ 1 " in output
