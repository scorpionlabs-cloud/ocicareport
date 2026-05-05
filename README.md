# OCI Compute Capacity Report (ocareport)

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![OCI SDK](https://img.shields.io/badge/OCI%20SDK-2.149.0+-orange.svg)](https://oracle-cloud-infrastructure-python-sdk.readthedocs.io/)

**Check Oracle Cloud Infrastructure compute capacity across regions, availability domains, and fault domains.**

`ocareport` is a command-line tool that queries the OCI Compute Capacity Report API for compute shape availability. It supports VM, bare metal, flex, and GPU shapes across one or more subscribed OCI regions.

The report is useful for capacity planning, GPU discovery, regional placement checks, and automation pipelines. Results can be rendered as a terminal table, JSON, or CSV.

## Features

- **Multi-region support** - Check your home region, one or more explicit regions, or all subscribed regions.
- **Multi-shape support** - Check one or more compute shapes in a single run.
- **Flex shape support** - Provide global or per-shape OCPU and memory sizing for flex shapes.
- **GPU discovery** - Search for A10, V100, A100, H100, L40S, and other GPU shapes across OCI.
- **Fault-domain granularity** - Reports availability by region, availability domain, and fault domain.
- **Capacity columns** - Shows `OCPU` and `MEMORY` for each result row.
- **Automation-friendly output** - Emit `table`, `json`, or `csv` using `--output`.
- **Partial failure handling** - Region, AD, FD, or shape errors are returned as `ERROR` rows instead of aborting the full scan.
- **Concurrent scans** - Use bounded workers with `--workers` to speed up large multi-region scans.
- **Flexible authentication** - Auto-detects Cloud Shell, OCI config file, or Instance Principals authentication.

## Quick Start

```bash
# Install from the project directory
pip install -e .

# Check a shape in your home region
ocareport -shape VM.Standard.E5.Flex

# Check GPU availability across all subscribed regions
ocareport -shape BM.GPU.H100.8 -region all --workers 8

# Check multiple shapes across multiple regions
ocareport \
  -shape VM.Standard.E5.Flex,BM.GPU.H100.8 \
  -region us-ashburn-1,eu-frankfurt-1 \
  --workers 8
```


## Usage Examples

### Check a shape in the home region

```bash
ocareport -shape VM.Standard.E5.Flex
```

### Check a specific region

```bash
ocareport -shape VM.Standard.E5.Flex -region eu-frankfurt-1
```

### Check multiple regions

```bash
# Comma-separated
ocareport -shape VM.Standard.E5.Flex -region ap-singapore-1,ap-singapore-2

# Repeated flag
ocareport -shape VM.Standard.E5.Flex -region ap-singapore-1 -region ap-singapore-2
```

### Check all subscribed regions

```bash
ocareport -shape VM.Standard.E5.Flex -region all --workers 8
```

### Check multiple shapes

```bash
# Comma-separated
ocareport -shape VM.Standard.E5.Flex,BM.GPU.H100.8

# Repeated flag
ocareport -shape VM.Standard.E5.Flex -shape BM.GPU.H100.8
```

### Check multiple shapes across multiple regions

```bash
ocareport \
  -shape VM.Standard.E5.Flex,VM.Standard.E4.Flex,VM.Standard.E6.Flex \
  -region ap-singapore-1,ap-singapore-2,ap-tokyo-1 \
  --workers 8
```

### Flex shape with global OCPU and memory

```bash
ocareport -shape VM.Standard.E5.Flex -ocpus 8 -memory 64
```

### Multiple flex shapes with different OCPU and memory values

Use `SHAPE:OCPUS:MEMORY_GB` for per-shape sizing:

```bash
ocareport \
  -shape VM.Standard.E5.Flex:8:64,VM.Standard.E4.Flex:4:32,VM.Standard.E6.Flex:16:128 \
  -region ap-singapore-1,ap-singapore-2
```

### Emit JSON

```bash
ocareport -shape VM.Standard.E5.Flex -region all --workers 8 --output json
```

### Emit CSV

```bash
ocareport -shape BM.GPU.H100.8 -region all --workers 8 --output csv > capacity.csv
```

## Output Columns

Table output contains the following columns:

| Column | Meaning |
|--------|---------|
| `REGION` | OCI region scanned. |
| `AVAILABILITY_DOMAIN` | Availability domain checked. |
| `FAULT_DOMAIN` | Fault domain checked. |
| `SHAPE` | Compute shape checked. |
| `OCPU` | OCPU capacity value for the row. If OCI exposes an exact capacity count, this is total available OCPU. If OCI only confirms availability, this is the requested/per-instance OCPU value confirmed available. |
| `MEMORY` | Memory capacity value for the row. If OCI exposes an exact capacity count, this is total available memory in GB. If OCI only confirms availability, this is the requested/per-instance memory value confirmed available. |
| `STATUS` | OCI capacity status. |
| `ERROR` | Error message for partial failures. Empty for successful rows. |

The table intentionally does **not** display OCI's available-count value. JSON and CSV output use the same capacity semantics for `ocpus` and `memory_gb`.

## Status Meanings

| Status | Description |
|--------|-------------|
| `AVAILABLE` | OCI reports capacity for the requested shape configuration. |
| `OUT_OF_HOST_CAPACITY` | OCI does not currently have enough host capacity for the requested shape configuration in that location. |
| `HARDWARE_NOT_SUPPORTED` | The required hardware is not deployed or not supported in that location. |
| `ERROR` | The check failed for that region, AD, FD, or shape. The `ERROR` column contains details. |

## Capacity Semantics

OCI may or may not expose an exact available-instance count depending on tenancy, region, and capacity-report behavior.

When OCI exposes an exact count, `ocareport` calculates:

```text
OCPU   = available_count * instance_ocpus
MEMORY = available_count * instance_memory_gb
```

When OCI returns `AVAILABLE` without an exact count, `ocareport` displays the requested/per-instance size as the confirmed numeric capacity value. This avoids non-numeric lower-bound output such as `>=1` while keeping the output automation-friendly.

For fixed shapes, per-instance OCPU and memory are resolved from OCI shape metadata where available. For flex shapes, the values come from `-ocpus`, `-memory`, or the per-shape `SHAPE:OCPUS:MEMORY_GB` syntax.


## Common GPU Shapes

| Shape | GPU | Count | Typical use case |
|-------|-----|------:|------------------|
| `VM.GPU.A10.1` | NVIDIA A10 | 1 | AI inference, graphics |
| `VM.GPU.A10.2` | NVIDIA A10 | 2 | AI inference, graphics |
| `VM.GPU3.1` | NVIDIA V100 | 1 | Deep learning, HPC |
| `VM.GPU3.2` | NVIDIA V100 | 2 | Deep learning, HPC |
| `VM.GPU3.4` | NVIDIA V100 | 4 | Deep learning, HPC |
| `BM.GPU4.8` | NVIDIA A100 40GB | 8 | Large AI models, HPC |
| `BM.GPU.A100-v2.8` | NVIDIA A100 80GB | 8 | LLM training, large models |
| `BM.GPU.H100.8` | NVIDIA H100 | 8 | LLM training, HPC |
| `BM.GPU.L40S.4` | NVIDIA L40S | 4 | AI inference, rendering |


### JSON or CSV output contains warnings or logs

Use the latest version of the project. Machine-readable output should write data to stdout and diagnostics to stderr.

### Some rows show `OUT_OF_HOST_CAPACITY`

That means OCI did not report enough capacity for that requested shape configuration in that region/AD/FD at the time of the check. Try another fault domain, availability domain, region, or smaller flex shape size.

### Some rows show `HARDWARE_NOT_SUPPORTED`

That shape is not supported in that location. Try another region or shape.

## Development

Install dependencies:

```bash
python3 -m pip install --user -e .
export PATH="$HOME/.local/bin:$PATH"
ocareport -shape VM.Standard.E5.Flex -ocpu 2 -memory 8 -region ap-singapore-1,ap-singapore-2
```

## Project Structure

```text
ocareport/
├── ocareport/
│   ├── __init__.py
│   ├── __main__.py
│   ├── cli.py            # Argument parsing and command orchestration
│   ├── capacity.py       # Capacity report API calls and concurrent scanning
│   ├── identity.py       # Authentication and OCI identity functions
│   ├── models.py         # Result dataclasses
│   ├── output.py         # table/json/csv renderers
│   └── utils.py          # Terminal colors and formatting
├── tests/                # Unit tests
├── requirements.txt      # Runtime dependencies
├── pyproject.toml        # Package configuration
├── LICENSE               # MIT License
├── README.md             # Project documentation
├── CHANGELOG.md          # Version history
└── CONTRIBUTING.md       # Contribution guidelines
```

## Credits

Inspired by Enrico Pesce - Project Link: [https://github.com/enricopesce/ocareport](https://github.com/enricopesce/ocareport)


