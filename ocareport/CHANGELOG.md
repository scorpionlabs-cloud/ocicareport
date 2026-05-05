# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.3.6] - 2026

### Changed
- Removed lower-bound markers from OCPU and MEMORY table output.
- JSON/CSV output no longer emits `capacity_is_lower_bound`.
- When OCI returns `AVAILABLE` without an exact `available_count`, OCPU and MEMORY now show the numeric requested/per-instance capacity confirmed available.

## [1.3.5] - 2026

### Changed
- Removed the `COUNT` column from table output.
- Removed `available_count` and `available_count_is_lower_bound` from JSON/CSV output.
- Kept OCPU and MEMORY as the primary total-capacity fields.

## [1.3.4] - 2026

### Fixed
- When OCI returns `AVAILABLE` but omits `available_count`, table output now shows lower-bound capacity values like `>=1` instead of blank cells.
- JSON/CSV output now includes `available_count_is_lower_bound` and `capacity_is_lower_bound` flags.

### Changed
- Clarified table notes and README documentation for exact capacity versus lower-bound capacity.

## [1.3.3] - 2026

### Added
- Added `available_count`, `instance_ocpus`, and `instance_memory_gb` to JSON/CSV output.
- Added a table `COUNT` column so operators can see how many new instances OCI reports for each row.

### Changed
- Changed table `OCPU` and `MEMORY` semantics to show total available capacity per row: `available_count * per-instance shape size`.
- Kept per-instance sizing available in machine-readable output for validation and downstream calculations.

## [1.3.2] - 2026

### Added
- Added per-shape flex sizing syntax: `-shape VM.Standard.E5.Flex:8:64`.
- Added automatic fixed-shape OCPU/memory resolution from OCI `list_shapes` metadata by region and availability domain.
- Added fallback fixed-shape sizing inference so rows do not misleadingly display flex defaults for fixed shapes when metadata lookup is unavailable.

### Changed
- Table titles no longer imply one global OCPU/memory value for all shapes.
- Result rows now display the effective requested or resolved OCPU/memory for each shape.

## [1.3.0] - 2026

### Added
- Added multiple shape support via repeated `-shape` flags or comma-separated shape values.
- Added multiple explicit region support via repeated `-region` flags or comma-separated region values.
- Multi-shape scans now check every requested shape across every selected region, availability domain, and fault domain.

### Changed
- Updated table, JSON, and CSV output paths to preserve a distinct `shape` value per result row.
- Kept backward-compatible single-shape and single-region CLI usage.

## [1.2.0] - 2026

### Added
- Added `--output table|json|csv` for automation-friendly output.
- Added `--workers` for bounded concurrent capacity checks.
- Added recoverable `ERROR` result rows so regional, AD, FD, or shape failures do not abort all-region scans by default.
- Added `--fail-fast` for operators who prefer the previous stop-on-error behavior.
- Added coverage-enabled test configuration and Ruff configuration.

### Changed
- Refactored the project into the `ocareport/` package with dedicated CLI, capacity, identity, model, output, and utility modules.
- Updated CI to install development dependencies, run tests with coverage, and run Ruff checks.
- Updated documentation and examples for the package entry point.

## [1.1.0] - 2024

### Added
- Auto-detect authentication mode (tries CloudShell, Config File, Instance Principals in order)
- Modular project structure with separate `modules/` directory
- Comprehensive unit tests in `test_ocareport.py`
- Support for flexible OCPU and memory configuration with `-ocpus` and `-memory` flags
- Rich terminal output with color-coded availability status
- Documentation with usage examples and GPU shape reference

### Changed
- Refactored authentication logic into `modules/identity.py`
- Improved error handling for authentication failures
- Enhanced CLI argument parsing

## [1.0.0] - 2024

### Added
- Initial release
- Query OCI Compute Capacity Report API
- Support for CloudShell, Config File, and Instance Principals authentication
- Check shape availability across regions, availability domains, and fault domains
- Support for checking all subscribed regions with `-region all`
- Color-coded terminal output
