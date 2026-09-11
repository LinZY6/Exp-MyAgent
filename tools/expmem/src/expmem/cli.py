"""CLI: python -m expmem <command>."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from expmem.tools import TOOL_SCHEMA, handle
from expmem.viz import serve as viz_serve


def _root(args: argparse.Namespace) -> str:
    return str(Path(args.root or os.environ.get("EXPMEM_ROOT") or "./expmem_data"))


def _print(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="expmem", description="Standalone experiment memory for Agents")
    p.add_argument("--root", help="data directory (default EXPMEM_ROOT or ./expmem_data)")
    p.add_argument("--project", default="default")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("schema", help="print tool schema for an Agent")
    s.set_defaults(func=lambda a: _print({"tools": TOOL_SCHEMA}))

    s = sub.add_parser("invoke", help="JSON in/out for Pi or any Agent tool bridge")
    s.add_argument("--action", required=True)
    s.add_argument("--params", default="{}", help="JSON object")
    s.set_defaults(
        func=lambda a: _print(handle(_root(a), a.action, json.loads(a.params or "{}"), project=a.project))
    )

    s = sub.add_parser("search-papers")
    s.add_argument("query")
    s.add_argument("--limit", type=int, default=5)
    s.set_defaults(
        func=lambda a: _print(handle(_root(a), "search_papers", {"query": a.query, "limit": a.limit}, project=a.project))
    )

    s = sub.add_parser("search", help="BM25 search: collection + keywords")
    s.add_argument("--collection", default="", help="dataset/project name or path to experiments.jsonl")
    s.add_argument("--keywords", required=True)
    s.add_argument("--kind", default="")
    s.add_argument("--paper", default="")
    s.add_argument("--upstream", default="")
    s.add_argument("--status", default="")
    s.add_argument("--fields", default="")
    s.add_argument("--top-k", type=int, default=8)
    s.set_defaults(
        func=lambda a: _print(
            handle(
                _root(a),
                "search_experiments",
                {
                    "collection": a.collection or a.project,
                    "keywords": a.keywords,
                    "kind": a.kind,
                    "paper": a.paper,
                    "upstream": a.upstream,
                    "status": a.status,
                    "fields": a.fields,
                    "top_k": a.top_k,
                },
                project=a.project,
            )
        )
    )

    s = sub.add_parser("retrieve")
    s.add_argument("query")
    s.add_argument("--kind", default="")
    s.add_argument("--paper", default="")
    s.set_defaults(
        func=lambda a: _print(
            handle(
                _root(a),
                "search_experiments",
                {"collection": a.project, "keywords": a.query, "kind": a.kind, "paper": a.paper},
                project=a.project,
            )
        )
    )

    s = sub.add_parser("create")
    s.add_argument("--kind", required=True)
    s.add_argument("--rationale", required=True)
    s.add_argument("--change", required=True)
    s.add_argument("--expected", default="")
    s.add_argument("--upstream", default="", help="comma-separated parent ids")
    s.add_argument("--papers", default="")
    s.add_argument("--force", action="store_true")
    s.set_defaults(
        func=lambda a: _print(
            handle(
                _root(a),
                "create_experiment",
                {
                    "kind": a.kind,
                    "rationale": a.rationale,
                    "change": a.change,
                    "expected": a.expected,
                    "upstream": [x.strip() for x in a.upstream.split(",") if x.strip()],
                    "papers": a.papers,
                    "force": a.force,
                },
                project=a.project,
            )
        )
    )

    s = sub.add_parser("viz", help="open HTML graph visualizer")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8765)
    s.add_argument("--no-browser", action="store_true")
    s.set_defaults(
        func=lambda a: viz_serve(
            host=a.host,
            port=a.port,
            open_browser=not a.no_browser,
            extra_roots=[Path(x) for x in [_root(a), os.environ.get("EXPMEM_ROOT")] if x],
        )
    )

    s = sub.add_parser("complete")
    s.add_argument("experiment_id")
    s.add_argument("--metrics", default="{}")
    s.add_argument("--verdict", default="")
    s.add_argument("--delta", type=float, default=None)
    s.add_argument("--failed", action="store_true")
    s.set_defaults(
        func=lambda a: _print(
            handle(
                _root(a),
                "complete_experiment",
                {
                    "experiment_id": a.experiment_id,
                    "metrics": a.metrics,
                    "verdict": a.verdict or None,
                    "delta": a.delta,
                    "failed": a.failed,
                },
                project=a.project,
            )
        )
    )

    args = p.parse_args(argv)
    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
