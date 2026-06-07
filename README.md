# Zespa Review Intelligence

MVP pipeline for comparing public Korean shopping product-card signals for Zespa/제스파 and Bodyfriend/바디프렌드.

The collector is intentionally conservative. It attempts low-rate public search-result collection from Naver Shopping and Coupang, records blocking/parser status in `data/source_status.json`, and never fabricates product or review data when a site blocks or returns an unsupported page.

## Files

- `config/search_terms.json`: brand seeds, source base URLs, and request delay.
- `scripts/collect.py`: public product-card collector.
- `scripts/analyze.py`: summary analyzer for dashboard/report output.
- `scripts/update-and-push.sh`: daily update wrapper with optional git push.
- `data/products.csv`: appended normalized product rows.
- `data/source_status.json`: per-source/per-query collection status.
- `data/latest.json`: dashboard JSON.
- `reports/latest-report.md`: latest markdown report.
- `public/index.html`: static dashboard.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Playwright is optional for the default smoke test. To enable the `--playwright` fallback:

```bash
python3 -m playwright install chromium
```

## Local Smoke Test

Run a low-rate dry run with the requested limits:

```bash
python3 scripts/collect.py --max-pages 1 --max-items 5
python3 scripts/analyze.py
```

Serve the repo root so the dashboard can fetch `data/latest.json`:

```bash
python3 -m http.server 8000
```

Open `http://localhost:8000/public/`.

If both shopping sources block or return DOM that cannot be parsed, the dashboard will show no product rows and `data/source_status.json` will contain the reason for each attempted query.

## Daily Update

```bash
MAX_PAGES=1 MAX_ITEMS=20 ./scripts/update-and-push.sh
```

To commit and push data updates from the wrapper:

```bash
PUSH_CHANGES=1 MAX_PAGES=1 MAX_ITEMS=20 ./scripts/update-and-push.sh
```

## Data Schema

`data/products.csv` contains:

```text
collected_at_kst, source, brand, query, rank, title, url, price, rating, review_count
```

Rows are appended. `scripts/analyze.py` defaults to analyzing only the latest run timestamp; pass `--all-history` to summarize every row in the CSV.
