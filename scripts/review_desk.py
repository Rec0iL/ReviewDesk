#!/usr/bin/env python3
"""Review Desk's command: `python3 <skill>/scripts/review_desk.py <command>`. See `desk/cli.py`."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from desk.cli import main  # noqa: E402

if __name__ == "__main__":
    main()
