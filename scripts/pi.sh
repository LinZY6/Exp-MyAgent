#!/usr/bin/env bash
# Launch Pi from this repo (macOS / Linux).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ -f "${ROOT}/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "${ROOT}/.env"
  set +a
fi

if [[ -z "${ANTHROPIC_AUTH_TOKEN:-}" && -n "${LLM_API_KEY:-}" ]]; then
  export ANTHROPIC_AUTH_TOKEN="$LLM_API_KEY"
fi

export EXPMEM_ROOT="${EXPMEM_ROOT:-${ROOT}/expmem_data}"
SRC="${ROOT}/tools/expmem/src"
if [[ -n "${PYTHONPATH:-}" ]]; then
  export PYTHONPATH="${SRC}:${PYTHONPATH}"
else
  export PYTHONPATH="${SRC}"
fi
export PYTHONUTF8=1
export EXPMEM_PYTHON="${EXPMEM_PYTHON:-python3}"

FIXTURES="${ROOT}/fixtures"
for name in rec_ctr seq_recall; do
  dest="${EXPMEM_ROOT}/${name}/experiments.jsonl"
  src="${FIXTURES}/${name}/experiments.jsonl"
  if [[ ! -f "$dest" && -f "$src" ]]; then
    mkdir -p "$(dirname "$dest")"
    cp "$src" "$dest"
  fi
done

PI_CLI="${ROOT}/node_modules/@earendil-works/pi-coding-agent/dist/cli.js"
if [[ ! -f "$PI_CLI" ]]; then
  echo "Pi not installed. Run: npm install" >&2
  exit 1
fi

PI_ARGS=("$@")
has_model=0
for a in "${PI_ARGS[@]+"${PI_ARGS[@]}"}"; do
  if [[ "$a" == "--model" || "$a" == "-m" || "$a" == --model=* ]]; then
    has_model=1
    break
  fi
done
if [[ -n "${PI_MODEL:-}" && "$has_model" -eq 0 ]]; then
  PI_ARGS=(--model "$PI_MODEL" "${PI_ARGS[@]+"${PI_ARGS[@]}"}")
fi

exec node "$PI_CLI" "${PI_ARGS[@]+"${PI_ARGS[@]}"}"
