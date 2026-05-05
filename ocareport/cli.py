# coding: utf-8
"""Command-line interface for ocareport."""

from __future__ import annotations

import argparse
import contextlib
import sys

import oci

from ocareport.capacity import build_scan_targets, create_capacity_report, scan_capacity
from ocareport.identity import get_region_subscription_list, init_authentication
from ocareport.output import render_results
from ocareport.shape_config import dedupe_shape_requests, is_flex_shape, parse_shape_request
from ocareport.utils import clear, green, print_error, print_info

VERSION = "1.0.0"

def positive_float(value):
    """Parse a positive float argument."""
    try:
        parsed_value = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"{value!r} is not a valid number") from exc

    if parsed_value <= 0:
        raise argparse.ArgumentTypeError("must be greater than 0")

    return parsed_value


def positive_int(value):
    """Parse a positive integer argument."""
    try:
        parsed_value = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"{value!r} is not a valid integer") from exc

    if parsed_value <= 0:
        raise argparse.ArgumentTypeError("must be greater than 0")

    return parsed_value


def parse_multi_value(values, *, argument_name):
    """Normalize repeated and comma-separated CLI values into a de-duplicated list."""
    if not values:
        return []

    normalized = []
    seen = set()
    for raw_value in values:
        for item in str(raw_value).split(","):
            value = item.strip()
            if not value:
                continue
            key = value.lower()
            if key not in seen:
                normalized.append(value)
                seen.add(key)

    return normalized


def parse_shape_values(values, *, default_ocpus, default_memory_gb, parser):
    """Parse shape CLI values into ShapeRequest objects."""
    raw_shapes = parse_multi_value(values, argument_name="-shape")
    requests = []
    for raw_shape in raw_shapes:
        try:
            requests.append(
                parse_shape_request(
                    raw_shape,
                    default_ocpus=default_ocpus,
                    default_memory_gb=default_memory_gb,
                )
            )
        except ValueError as exc:
            parser.error(f"invalid -shape value {raw_shape!r}: {exc}")
    return dedupe_shape_requests(requests)


def parse_arguments(argv=None):
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Check OCI compute shape availability across regions",
    )

    parser.add_argument(
        "-auth",
        default="",
        dest="auth_method",
        choices=["cs", "cf", "ip", ""],
        help="Authentication method: 'cs' CloudShell, 'cf' config file, 'ip' instance principals",
    )
    parser.add_argument(
        "-config_file",
        default="~/.oci/config",
        dest="config_file_path",
        help="Path to OCI config file (default: ~/.oci/config)",
    )
    parser.add_argument(
        "-profile",
        default="DEFAULT",
        dest="config_profile",
        help="Config file profile section (default: DEFAULT)",
    )
    parser.add_argument(
        "-region",
        action="append",
        default=None,
        dest="region_values",
        help=(
            "Region to analyze: specific region name, 'all', or empty for home region. "
            "Repeat the flag or use comma-separated values for multiple regions."
        ),
    )
    parser.add_argument(
        "-shape",
        action="append",
        default=None,
        dest="shape_values",
        required=True,
        help=(
            "Compute shape name to check. Repeat the flag or use comma-separated "
            "values for multiple shapes. Flex sizes can be supplied per shape as "
            "SHAPE:OCPUS:MEMORY_GB, for example VM.Standard.E5.Flex:8:64."
        ),
    )
    parser.add_argument(
        "-ocpus",
        type=positive_float,
        default=1.0,
        dest="ocpu",
        help="OCPU count for flex shapes (default: 1)",
    )
    parser.add_argument(
        "-memory",
        type=positive_float,
        default=1.0,
        dest="memory",
        help="Memory in GB for flex shapes (default: 1)",
    )
    parser.add_argument(
        "--output",
        choices=["table", "json", "csv"],
        default="table",
        help="Output format (default: table)",
    )
    parser.add_argument(
        "--workers",
        type=positive_int,
        default=1,
        help="Number of concurrent capacity checks (default: 1)",
    )
    parser.add_argument(
        "--fail-fast",
        action="store_true",
        help="Stop on region metadata failures instead of returning partial results",
    )
    parser.add_argument(
        "--no-clear",
        action="store_true",
        help="Do not clear the terminal before rendering table output",
    )

    args = parser.parse_args(argv)
    args.shape_requests = parse_shape_values(
        args.shape_values,
        default_ocpus=args.ocpu,
        default_memory_gb=args.memory,
        parser=parser,
    )
    args.shapes = [request.name for request in args.shape_requests]
    args.regions = parse_multi_value(args.region_values, argument_name="-region")
    if not args.shapes:
        parser.error("-shape requires at least one non-empty value")

    # Backward-compatible string attributes for existing callers/tests.
    args.shape = ",".join(args.shapes)
    args.region = ",".join(args.regions) if args.regions else ""
    return args


def _print_banner(args, tenancy, auth_name, details):
    """Print the human-readable banner for table output."""
    print(green(f"\n{'*' * 94}"))
    print_info(green, "Script", "version", VERSION)
    print_info(green, "Login", "success", auth_name)
    print_info(green, "Login", "profile", details)
    print_info(green, "Tenancy", tenancy.name, f"home region: {tenancy.home_region_key}")
    print_info(green, "Shapes", "analyzed", ", ".join(args.shapes))
    flex_requests = [request for request in args.shape_requests if is_flex_shape(request.name)]
    if flex_requests:
        sizes = sorted({(request.ocpus, request.memory_gb) for request in flex_requests})
        size_label = ", ".join(f"{ocpus:g} OCPU/{memory:g} GB" for ocpus, memory in sizes)
        print_info(green, "Flex size", "requested", size_label)
    print(green(f"{'*' * 94}\n"))


def _build_targets_with_partial_errors(config, signer, tenancy_id, regions, args):
    """Build scan targets and convert per-region metadata failures into result rows."""
    targets = []
    metadata_errors = []
    for region in regions:
        try:
            targets.extend(build_scan_targets(config, signer, tenancy_id, [region]))
        except oci.exceptions.ServiceError as exc:
            message = getattr(exc, "message", str(exc))
            if args.fail_fast:
                raise
            from ocareport.models import CapacityResult

            for request in args.shape_requests:
                metadata_errors.append(
                    CapacityResult(
                        region=region.region_name,
                        availability_domain="",
                        fault_domain="",
                        shape=request.name,
                        ocpus=request.ocpus,
                        memory_gb=request.memory_gb,
                        status="ERROR",
                        error=f"Region metadata failure: {message}",
                    )
                )
    return targets, metadata_errors

def _stdout_for_format(output):
    """Keep JSON/CSV data clean on stdout while preserving diagnostics on stderr."""
    if output == "table":
        return contextlib.nullcontext()
    return contextlib.redirect_stdout(sys.stderr)


def main(argv=None):
    """Main entry point."""
    args = parse_arguments(argv)
    if args.output == "table" and not args.no_clear:
        clear()

    with _stdout_for_format(args.output):
        config, signer, tenancy, auth_name, details, tenancy_id = init_authentication(
            args.auth_method,
            args.config_file_path,
            args.config_profile,
        )

        if args.output == "table":
            print("\r" + " " * 60 + "\r", end="", flush=True)
            _print_banner(args, tenancy, auth_name, details)

        identity_client = oci.identity.IdentityClient(config=config, signer=signer)
        regions = get_region_subscription_list(identity_client, tenancy_id, args.regions)

        try:
            targets, metadata_errors = _build_targets_with_partial_errors(
                config, signer, tenancy_id, regions, args
            )
        except oci.exceptions.ServiceError as exc:
            print_error("Region metadata error", getattr(exc, "message", str(exc)))
            return 4

    results = metadata_errors + scan_capacity(
        config=config,
        signer=signer,
        tenancy_id=tenancy_id,
        targets=targets,
        shape_requests=args.shape_requests,
        ocpu=args.ocpu,
        memory=args.memory,
        workers=args.workers,
    )

    render_results(results, output=args.output, shapes=args.shapes, ocpu=args.ocpu, memory=args.memory)

    if any(result.error for result in results):
        return 5
    if any(result.status == "AVAILABLE" for result in results):
        return 0
    return 1


__all__ = [
    "VERSION",
    "create_capacity_report",
    "is_flex_shape",
    "main",
    "parse_arguments",
    "parse_multi_value",
    "positive_float",
    "positive_int",
]


if __name__ == "__main__":
    raise SystemExit(main())
