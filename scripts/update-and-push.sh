#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

python3 scripts/collect.py --max-pages "${MAX_PAGES:-1}" --max-items "${MAX_ITEMS:-20}"
python3 scripts/analyze.py
python3 scripts/collect_social.py --max-pages "${SOCIAL_MAX_PAGES:-1}" --max-items "${SOCIAL_MAX_ITEMS:-10}"
python3 scripts/analyze_social.py

if [[ "${PUSH_CHANGES:-0}" == "1" ]]; then
  git add config/search_terms.json config/social_sources.json data/products.csv data/source_status.json data/latest.json data/social_mentions.csv data/social_source_status.json data/social_latest.json reports/latest-report.md reports/social-latest-report.md public/index.html index.html README.md requirements.txt scripts/collect.py scripts/analyze.py scripts/collect_social.py scripts/analyze_social.py scripts/update-and-push.sh
  if ! git diff --cached --quiet; then
    git commit -m "Update review and social intelligence data"
    git push
  fi
fi
