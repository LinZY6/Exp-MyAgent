"""Papers pack (embeddable CPython)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from papers.tools import handle  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    params: dict = {}
    if "--params" in argv:
        i = argv.index("--params")
        params = json.loads(argv[i + 1] if i + 1 < len(argv) else "{}")
    elif argv:
        params = json.loads(argv[0])
    print(json.dumps(handle(params), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
