#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from harness.claude_adapter import run_adapter


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit('Usage: adapter_claude.py <run_request.json>')
    return run_adapter(Path(sys.argv[1]))


if __name__ == '__main__':
    raise SystemExit(main())
