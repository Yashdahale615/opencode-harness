#!/usr/bin/env python3
"""commands/verify.py - thin wrapper; real logic is in harness.entry.cli_verify."""
import sys
from harness.entry import cli_verify
raise SystemExit(cli_verify(sys.argv[1:]))
