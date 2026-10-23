#!/usr/bin/env python3
"""commands/run.py - thin wrapper; real logic is in harness.entry.cli_run."""
import sys
from harness.entry import cli_run
raise SystemExit(cli_run(sys.argv[1:]))
