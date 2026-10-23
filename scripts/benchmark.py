#!/usr/bin/env python3
"""scripts/benchmark.py - benchmark suite runner stub.

Intended to drive src/harness/controller.py over every task in a
benchmarks/datasets/ dataset (via benchmarks/runners/) and report
pass/fail. No datasets or runners are implemented yet.
"""
import sys


def main(argv=None) -> int:
    print("no benchmark datasets defined yet - see benchmarks/datasets/README.md")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
