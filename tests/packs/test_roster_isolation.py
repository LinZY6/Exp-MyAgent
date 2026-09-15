"""Isolation: roster must not import expmem or fnfit."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_no_expmem_or_fnfit_import():
    src = ROOT / "tools" / "roster" / "src" / "roster"
    for path in src.glob("*.py"):
        for line in path.read_text(encoding="utf-8").splitlines():
            s = line.strip()
            if s.startswith("import expmem") or s.startswith("from expmem"):
                raise AssertionError(path.name)
            if s.startswith("import fnfit") or s.startswith("from fnfit"):
                raise AssertionError(path.name)
            if s.startswith("import papers") or s.startswith("from papers"):
                raise AssertionError(path.name)


if __name__ == "__main__":
    test_no_expmem_or_fnfit_import()
    print("ok test_roster_isolation")
