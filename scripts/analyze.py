#!/usr/bin/env python3
"""Analyze collected product rows and publish dashboard/report data."""

from __future__ import annotations

import argparse
import csv
import json
import statistics
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
REPORTS_DIR = ROOT / "reports"
PRODUCTS_PATH = DATA_DIR / "products.csv"
STATUS_PATH = DATA_DIR / "source_status.json"
LATEST_PATH = DATA_DIR / "latest.json"
REPORT_PATH = REPORTS_DIR / "latest-report.md"

KEYWORDS = [
    "온열",
    "무선",
    "저소음",
    "소음",
    "가성비",
    "부모님",
    "선물",
    "시원",
    "강도",
    "공기압",
    "목",
    "어깨",
    "발",
    "종아리",
    "허리",
    "안마의자",
    "마사지건",
    "AS",
    "배송",
    "내구성",
    "프리미엄",
    "팔콘",
]


def now_kst() -> str:
    return datetime.now(ZoneInfo("Asia/Seoul")).isoformat(timespec="seconds")


def parse_float(value: str) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_int(value: str) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def load_rows() -> list[dict[str, str]]:
    if not PRODUCTS_PATH.exists():
        return []
    with PRODUCTS_PATH.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def latest_run_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    if not rows:
        return []
    latest_stamp = max(row.get("collected_at_kst", "") for row in rows)
    return [row for row in rows if row.get("collected_at_kst") == latest_stamp]


def summarize_brands(rows: list[dict[str, str]]) -> dict[str, dict[str, object]]:
    by_brand: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        by_brand[row.get("brand", "Unknown")].append(row)

    summary: dict[str, dict[str, object]] = {}
    for brand, brand_rows in sorted(by_brand.items()):
        ratings = [value for value in (parse_float(row.get("rating", "")) for row in brand_rows) if value is not None]
        review_total = sum(parse_int(row.get("review_count", "")) for row in brand_rows)
        prices = [parse_int(row.get("price", "")) for row in brand_rows if parse_int(row.get("price", ""))]
        top_products = sorted(
            brand_rows,
            key=lambda row: (parse_int(row.get("review_count", "")), parse_float(row.get("rating", "")) or 0),
            reverse=True,
        )[:8]
        summary[brand] = {
            "product_count": len(brand_rows),
            "avg_rating": round(statistics.fmean(ratings), 2) if ratings else None,
            "total_review_count": review_total,
            "avg_price": round(statistics.fmean(prices)) if prices else None,
            "top_products": top_products,
        }
    return summary


def summarize_channels(rows: list[dict[str, str]]) -> dict[str, dict[str, object]]:
    by_source: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        by_source[row.get("source", "unknown")].append(row)
    return {
        source: {
            "product_count": len(source_rows),
            "total_review_count": sum(parse_int(row.get("review_count", "")) for row in source_rows),
            "brands": sorted({row.get("brand", "Unknown") for row in source_rows}),
            "queries": sorted({row.get("query", "") for row in source_rows if row.get("query")}),
        }
        for source, source_rows in sorted(by_source.items())
    }


def keyword_counts(rows: list[dict[str, str]]) -> dict[str, int]:
    haystack = " ".join(row.get("title", "") for row in rows)
    counts = Counter()
    for keyword in KEYWORDS:
        count = haystack.lower().count(keyword.lower())
        if count:
            counts[keyword] = count
    return dict(counts.most_common())


def load_status() -> dict[str, object]:
    if not STATUS_PATH.exists():
        return {"updated_at_kst": None, "sources": []}
    return json.loads(STATUS_PATH.read_text(encoding="utf-8"))


def write_report(latest: dict[str, object]) -> None:
    REPORTS_DIR.mkdir(exist_ok=True)
    brands = latest["brands"]
    channels = latest["channels"]
    lines = [
        "# Zespa vs Bodyfriend latest report",
        "",
        f"- Updated at KST: {latest['updated_at_kst']}",
        f"- Rows in latest run: {latest['row_count']}",
        f"- Historical rows: {latest['historical_row_count']}",
        "",
        "## Brand summary",
    ]
    if not brands:
        lines.append("")
        lines.append("No product rows are available. Check `data/source_status.json` for source blocking or parser status.")
    for brand, item in brands.items():
        lines.extend(
            [
                "",
                f"### {brand}",
                f"- Product rows: {item['product_count']}",
                f"- Average rating: {item['avg_rating'] if item['avg_rating'] is not None else 'n/a'}",
                f"- Total review count: {item['total_review_count']}",
                f"- Average price: {item['avg_price'] if item['avg_price'] is not None else 'n/a'}",
            ]
        )
    lines.extend(["", "## Channel coverage"])
    if not channels:
        lines.append("")
        lines.append("No channel coverage yet.")
    for source, item in channels.items():
        lines.append(f"- {source}: {item['product_count']} rows, {item['total_review_count']} reviews")

    lines.extend(["", "## Keyword counts"])
    keyword_data = latest["keywords"]
    if keyword_data:
        lines.extend(f"- {keyword}: {count}" for keyword, count in keyword_data.items())
    else:
        lines.append("- No keywords detected from available titles/review snippets.")

    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def analyze(args: argparse.Namespace) -> int:
    rows = load_rows()
    scoped_rows = rows if args.all_history else latest_run_rows(rows)
    latest = {
        "updated_at_kst": now_kst(),
        "row_count": len(scoped_rows),
        "historical_row_count": len(rows),
        "scope": "all_history" if args.all_history else "latest_run",
        "brands": summarize_brands(scoped_rows),
        "channels": summarize_channels(scoped_rows),
        "keywords": keyword_counts(scoped_rows),
        "source_status": load_status(),
    }
    DATA_DIR.mkdir(exist_ok=True)
    LATEST_PATH.write_text(json.dumps(latest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_report(latest)
    print(f"Analyzed {len(scoped_rows)} rows; wrote {LATEST_PATH.relative_to(ROOT)} and {REPORT_PATH.relative_to(ROOT)}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyze collected shopping product rows.")
    parser.add_argument("--all-history", action="store_true", help="Analyze every row in data/products.csv instead of the latest run only.")
    return analyze(parser.parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
