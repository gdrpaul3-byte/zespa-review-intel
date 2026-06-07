#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

python3 scripts/collect.py --max-pages "${MAX_PAGES:-1}" --max-items "${MAX_ITEMS:-20}"
python3 scripts/analyze.py

if [[ "${PUSH_CHANGES:-0}" == "1" ]]; then
  git add config/search_terms.json data/products.csv data/source_status.json data/latest.json reports/latest-report.md public/index.html README.md requirements.txt scripts/collect.py scripts/analyze.py scripts/update-and-push.sh
  if ! git diff --cached --quiet; then
    git commit -m "Update shopping review intelligence data"
    git push
  fi
fi
