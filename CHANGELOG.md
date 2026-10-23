# Changelog

All notable changes to this project are documented in this file.
The format follows [Keep a Changelog](https://keepachangelog.com/).

## [Unreleased]

### Added
- Restructured the reference implementation into the `opencode-harness`
  repository layout (`src/harness`, `tests/{unit,security,...}`,
  `commands/`, `profiles/`, `docs/`, etc.).

## [0.1.0] - 2026-09-24

### Added
- Initial reference implementation: contracts, permission policy,
  contained execution, workspace snapshotting, verification catalog +
  runtime, pure gate decision, evidence/receipt, hash-chained trace,
  budgeted context selection, model/profile routing.
- `docs/verified_execution_harness.pdf` - 26-page architecture reference.
- `test_all.py` / `test_more.py` executable tests against real files and
  processes.
