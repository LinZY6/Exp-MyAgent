"""Run spfit without relying on PYTHONPATH."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

_PACK_SRC = Path(__file__).resolve().parent / "src"
_REPO = Path(__file__).resolve().parents[2]


def _session_lab() -> str:
    env = (os.environ.get("EXPERIMENT_LAB") or "").strip()
    if env:
        return env
    p = _REPO / ".pi" / "lab-session.json"
    if not p.is_file():
        return ""
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    return str((data or {}).get("lab") or "").strip()


sys.path.insert(0, str(_PACK_SRC))
_lab = _session_lab()
if _lab:
    _lab_src = Path(_lab) / "src"
    if _lab_src.is_dir():
        sys.path.insert(0, str(_lab_src))

from spfit.tools import handle  # noqa: E402


def _patch_gate(lab: str) -> dict | None:
    if not lab:
        return None
    sys.path.insert(0, str(_REPO / "tools" / "lab" / "src"))
    from lab.codehash import check_run  # noqa: E402

    out = check_run(Path(lab))
    if not out.get("ok"):
        return out
    from lab.hat import require_hat  # noqa: E402

    hat = require_hat(Path(lab), {"reviewer"}, "run_spfit")
    if hat:
        return hat
    return None


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    params: dict = {}
    if "--params" in argv:
        i = argv.index("--params")
        raw = argv[i + 1] if i + 1 < len(argv) else "{}"
        params = json.loads(raw or "{}")
    elif argv:
        params = json.loads(argv[0])
    blocked = _patch_gate(_session_lab())
    if blocked is not None:
        blocked["experiment_id"] = str(params.get("experiment_id") or "")
        print(json.dumps(blocked, ensure_ascii=False))
        return 0
    print(json.dumps(handle(params), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
