# Zespa Review Intelligence

MVP pipeline for comparing public Korean shopping product-card signals and no-login social/community mentions for Zespa/제스파 and Bodyfriend/바디프렌드.

The collectors are intentionally conservative. The shopping collector attempts low-rate public search-result collection from Naver Shopping, Coupang, and Danawa. The social collector uses public Daum search HTML, Jina Reader fallbacks, optional YouTube search through `yt-dlp`, optional Reddit search through `rdt`, and configured RSS feeds. Blocked, missing, or unsupported sources are recorded in status files and never produce fabricated rows.

## Files

- `config/search_terms.json`: brand seeds, source base URLs, and request delay.
- `config/social_sources.json`: social/community query seeds, no-login site-search targets, optional CLI/RSS source config.
- `scripts/collect.py`: public product-card collector.
- `scripts/analyze.py`: summary analyzer for dashboard/report output.
- `scripts/collect_social.py`: public social/community mention collector.
- `scripts/analyze_social.py`: deterministic keyword classifier and social summary analyzer.
- `scripts/update-and-push.sh`: daily update wrapper with optional git push.
- `data/products.csv`: appended normalized product rows.
- `data/source_status.json`: per-source/per-query collection status.
- `data/latest.json`: dashboard JSON.
- `data/social_mentions.csv`: appended normalized social/community mention rows.
- `data/social_source_status.json`: per-source/per-query social collection status.
- `data/social_latest.json`: dashboard JSON for social/community voice.
- `reports/latest-report.md`: latest markdown report.
- `reports/social-latest-report.md`: latest social/community markdown report.
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
python3 scripts/collect_social.py --max-pages 1 --max-items 2 --delay 0.5
python3 scripts/analyze_social.py
```

Serve the repo root so the dashboard can fetch `data/latest.json`:

```bash
python3 -m http.server 8000
```

Open `http://localhost:8000/public/`.

If sources block or return DOM that cannot be parsed, the dashboard will show no rows for that area and the relevant status file will contain the reason for each attempted query.

## Daily Update

```bash
MAX_PAGES=1 MAX_ITEMS=20 ./scripts/update-and-push.sh
```

Social limits can be tuned separately:

```bash
SOCIAL_MAX_PAGES=1 SOCIAL_MAX_ITEMS=10 MAX_PAGES=1 MAX_ITEMS=20 ./scripts/update-and-push.sh
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

`data/social_mentions.csv` contains:

```text
collected_at_kst, platform, source_name, source_method, brand, query, title, snippet, url, author, published_at, engagement_score, sentiment, mention_type, product_cluster, raw_status
```

`scripts/analyze_social.py` fills `sentiment`, `mention_type`, and `product_cluster` with deterministic Korean/English keyword rules. It does not call an LLM. It defaults to the latest run timestamp; pass `--all-history` to summarize every social row.

The social collector does not log in, does not scrape private/member-only pages, and does not directly scrape Instagram, Threads, Naver Cafe, DCInside, Ppomppu, Clien, or TheQoo. Those platforms are represented through public Daum/Jina `site:` search result metadata only.
