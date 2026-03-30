#!/usr/bin/env python3
"""Runner wrapper that ensures project root is on `sys.path` then executes a script.

Usage:
  python bin/runner.py scripts/test_backtester.py -- --arg1 value

This replaces per-script `sys.path` hacks; prefer running scripts through this
wrapper when executing them directly from the repository root.
"""
from __future__ import annotations

import argparse
import os
import runpy
import sys


def main():
    parser = argparse.ArgumentParser(description='Run a repository script with project root on sys.path')
    parser.add_argument('script', help='Path to script relative to project root (e.g. scripts/test_backtester.py)')
    parser.add_argument('script_args', nargs=argparse.REMAINDER, help='Arguments passed to the target script')
    args = parser.parse_args()

    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

    script_path = os.path.abspath(os.path.join(project_root, args.script))
    if not os.path.exists(script_path):
        print(f'Script not found: {script_path}', file=sys.stderr)
        sys.exit(2)

    # Set argv for the target script
    sys.argv = [args.script] + args.script_args

    # Execute the script as __main__
    runpy.run_path(script_path, run_name='__main__')


if __name__ == '__main__':
    main()
