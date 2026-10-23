#!/usr/bin/env python3
"""commands/evaluate.py - thin wrapper; real logic is in harness.entry.cli_evaluate."""
import sys
from harness.entry import cli_evaluate
raise SystemExit(cli_evaluate(sys.argv[1:]))
