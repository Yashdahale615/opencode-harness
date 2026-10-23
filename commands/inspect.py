#!/usr/bin/env python3
"""commands/inspect.py - thin wrapper; real logic is in harness.entry.cli_inspect."""
import sys
from harness.entry import cli_inspect
raise SystemExit(cli_inspect(sys.argv[1:]))
