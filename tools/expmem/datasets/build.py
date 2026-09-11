"""Launcher: python datasets/build.py (from the expmem repo root)."""

from __future__ import annotations

import sys
from pathlib import Path

src = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(src))

from expmem.datasets.build import main  # noqa: E402

if __name__ == "__main__":
    main()
