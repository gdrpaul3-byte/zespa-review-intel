#!/usr/bin/env python3
"""Analyze public social/community mentions with deterministic classifiers."""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
REPORTS_DIR = ROOT / "reports"
MENTIONS_PATH = DATA_DIR / "social_mentions.csv"
STATUS_PATH = DATA_DIR / "social_source_status.json"
LATEST_PATH = DATA_DIR / "social_latest.json"
REPORT_PATH = REPORTS_DIR / "social-latest-report.md"

FIELDNAMES = [
    "collected_at_kst",
    "platform",
    "source_name",
    "source_method",
    "brand",
    "query",
    "title",
    "snippet",
    "url",
    "author",
    "published_at",
    "engagement_score",
    "sentiment",
    "mention_type",
    "product_cluster",
    "raw_status",
]

POSITIVE = ["좋", "추천", "만족", "시원", "효과", "가성비", "편하", "잘 샀", "괜찮", "튼튼", "선물 성공", "강추"]
NEGATIVE = ["별로", "불만", "고장", "AS", "a/s", "환불", "반품", "소음", "아프", "실망", "최악", "비추", "불량", "약하", "비싸", "후회"]

MENTION_TYPES = [
    ("AS/고장 불만", ["고장", "AS", "a/s", "수리", "불량", "환불", "반품", "내구성"]),
    ("구매 전 질문", ["살까요", "어때", "어떤가", "괜찮나요", "질문", "문의", "고민"]),
    ("추천 요청", ["추천", "골라", "뭐가 좋", "찾고", "알려"]),
    ("비교 질문", ["비교", "vs", "VS", "차이", "둘 중", "제스파 바디프렌드", "바디프렌드 제스파"]),
    ("선물/부모님 관련", ["부모님", "엄마", "아빠", "어버이", "선물", "효도"]),
    ("바이럴/광고 의심", ["협찬", "광고", "체험단", "파트너스", "제공받"]),
    ("중고/리퍼/렌탈", ["중고", "리퍼", "렌탈", "당근", "미개봉"]),
    ("구매 후기", ["후기", "샀", "구매", "사용기", "리뷰", "도착", "한달"]),
]

CLUSTERS = [
    ("발마사지기", ["발마사지", "발 마사지", "풋", "foot"]),
    ("종아리 마사지기", ["종아리", "leg", "다리"]),
    ("목/어깨 마사지기", ["목", "어깨", "neck", "shoulder"]),
    ("안마의자", ["안마의자", "마사지체어", "massage chair", "팔콘", "파라오"]),
    ("마사지건", ["마사지건", "massage gun", "건"]),
    ("온열/공기압", ["온열", "열", "공기압", "에어"]),
    ("부모님 선물", ["부모님", "엄마", "아빠", "어버이", "효도", "선물"]),
    ("AS/고장/내구성", ["AS", "a/s", "고장", "수리", "내구성", "불량"]),
    ("가격/가성비", ["가격", "가성비", "저렴", "할인", "비싸", "특가"]),
]

KEYWORDS = ["제스파", "바디프렌드", "바디프랜드", "부모님", "선물", "가성비", "고장", "AS", "추천", "후기", "발마사지기", "종아리", "안마의자", "팔콘", "온열", "공기압", "렌탈", "소음"]


def now_kst() -> str:
    return datetime.now(ZoneInfo("Asia/Seoul")).isoformat(timespec="seconds")


def load_rows() -> list[dict[str, str]]:
    if not MENTIONS_PATH.exists():
        return []
    with MENTIONS_PATH.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_rows(rows: list[dict[str, str]]) -> None:
    if not rows:
        return
    with MENTIONS_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in FIELDNAMES})


def latest_run_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    if not rows:
        return []
    latest_stamp = max(row.get("collected_at_kst", "") for row in rows)
    return [row for row in rows if row.get("collected_at_kst") == latest_stamp]


def text_for(row: dict[str, str]) -> str:
    return f"{row.get('title', '')} {row.get('snippet', '')} {row.get('query', '')}"


def classify_sentiment(text: str) -> str:
    if not text.strip():
        return "unknown"
    positive = sum(1 for keyword in POSITIVE if keyword.lower() in text.lower())
    negative = sum(1 for keyword in NEGATIVE if keyword.lower() in text.lower())
    if positive and negative:
        return "mixed"
    if positive:
        return "positive"
    if negative:
        return "negative"
    return "neutral"


def classify_from_rules(text: str, rules: list[tuple[str, list[str]]], default: str) -> str:
    lowered = text.lower()
    for label, keywords in rules:
        if any(keyword.lower() in lowered for keyword in keywords):
            return label
    return default


def enrich_rows(rows: list[dict[str, str]]) -> bool:
    changed = False
    for row in rows:
        text = text_for(row)
        sentiment = classify_sentiment(text)
        mention_type = classify_from_rules(text, MENTION_TYPES, "기타" if text.strip() else "unknown")
        cluster = classify_from_rules(text, CLUSTERS, "기타" if text.strip() else "unknown")
        for key, value in (("sentiment", sentiment), ("mention_type", mention_type), ("product_cluster", cluster)):
            if row.get(key) != value:
                row[key] = value
                changed = True
    return changed


def counter_map(rows: list[dict[str, str]], field: str) -> dict[str, int]:
    return dict(Counter(row.get(field, "unknown") or "unknown" for row in rows).most_common())


def summarize_brands(rows: list[dict[str, str]]) -> dict[str, dict[str, object]]:
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        grouped[row.get("brand", "Unknown") or "Unknown"].append(row)
    summary = {}
    for brand, brand_rows in sorted(grouped.items()):
        summary[brand] = {
            "mention_count": len(brand_rows),
            "sentiment": counter_map(brand_rows, "sentiment"),
            "mention_types": counter_map(brand_rows, "mention_type"),
            "product_clusters": counter_map(brand_rows, "product_cluster"),
        }
    return summary


def keyword_counts(rows: list[dict[str, str]]) -> dict[str, int]:
    haystack = " ".join(text_for(row) for row in rows)
    counts = Counter()
    for keyword in KEYWORDS:
        count = len(re.findall(re.escape(keyword), haystack, flags=re.IGNORECASE))
        if count:
            counts[keyword] = count
    return dict(counts.most_common(20))


def top_mentions(rows: list[dict[str, str]], limit: int = 12) -> list[dict[str, str]]:
    def score(row: dict[str, str]) -> int:
        try:
            engagement = int(float(row.get("engagement_score") or 0))
        except ValueError:
            engagement = 0
        weight = 50 if row.get("sentiment") == "negative" else 0
        return engagement + weight

    keep_fields = ["platform", "brand", "title", "snippet", "url", "author", "published_at", "engagement_score", "sentiment", "mention_type", "product_cluster"]
    return [{field: row.get(field, "") for field in keep_fields} for row in sorted(rows, key=score, reverse=True)[:limit]]


def fresh_signals(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    priority_types = {"AS/고장 불만", "비교 질문", "추천 요청", "선물/부모님 관련"}
    selected = [row for row in rows if row.get("sentiment") == "negative" or row.get("mention_type") in priority_types]
    return top_mentions(selected, limit=8)


def load_status() -> dict[str, object]:
    if not STATUS_PATH.exists():
        return {"updated_at_kst": None, "sources": []}
    return json.loads(STATUS_PATH.read_text(encoding="utf-8"))


def write_report(latest: dict[str, object]) -> None:
    REPORTS_DIR.mkdir(exist_ok=True)
    lines = [
        "# Social/community latest report",
        "",
        f"- Updated at KST: {latest['updated_at_kst']}",
        f"- Rows in latest scope: {latest['row_count']}",
        f"- Historical rows: {latest['historical_row_count']}",
        f"- Scope: {latest['scope']}",
        "",
        "## Brand mentions",
    ]
    brands = latest["brands"]
    if not brands:
        lines.append("")
        lines.append("No social rows are available. Check `data/social_source_status.json` for source blocking, missing optional CLIs, or parser status.")
    for brand, item in brands.items():
        lines.extend(
            [
                "",
                f"### {brand}",
                f"- Mentions: {item['mention_count']}",
                f"- Sentiment: {item['sentiment']}",
                f"- Mention types: {item['mention_types']}",
                f"- Product clusters: {item['product_clusters']}",
            ]
        )
    lines.extend(["", "## Platform coverage"])
    platforms = latest["platforms"]
    if platforms:
        lines.extend(f"- {platform}: {count}" for platform, count in platforms.items())
    else:
        lines.append("- No platform rows yet.")
    lines.extend(["", "## Top keywords"])
    keywords = latest["keywords"]
    if keywords:
        lines.extend(f"- {keyword}: {count}" for keyword, count in keywords.items())
    else:
        lines.append("- No configured keywords detected.")
    lines.extend(["", "## Fresh signals"])
    signals = latest["fresh_signals"]
    if signals:
        for row in signals:
            lines.append(f"- [{row.get('platform')}] {row.get('brand')} · {row.get('sentiment')} · {row.get('mention_type')} · {row.get('title')} · {row.get('url')}")
    else:
        lines.append("- No priority signals in the latest scope.")
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def analyze(args: argparse.Namespace) -> int:
    rows = load_rows()
    changed = enrich_rows(rows)
    if changed:
        write_rows(rows)
    scoped_rows = rows if args.all_history else latest_run_rows(rows)
    latest = {
        "updated_at_kst": now_kst(),
        "row_count": len(scoped_rows),
        "historical_row_count": len(rows),
        "scope": "all_history" if args.all_history else "latest_run",
        "brands": summarize_brands(scoped_rows),
        "platforms": counter_map(scoped_rows, "platform"),
        "sentiment": counter_map(scoped_rows, "sentiment"),
        "mention_types": counter_map(scoped_rows, "mention_type"),
        "product_clusters": counter_map(scoped_rows, "product_cluster"),
        "keywords": keyword_counts(scoped_rows),
        "top_mentions": top_mentions(scoped_rows),
        "fresh_signals": fresh_signals(scoped_rows),
        "source_status": load_status(),
    }
    DATA_DIR.mkdir(exist_ok=True)
    LATEST_PATH.write_text(json.dumps(latest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_report(latest)
    print(f"Analyzed {len(scoped_rows)} social rows; wrote {LATEST_PATH.relative_to(ROOT)} and {REPORT_PATH.relative_to(ROOT)}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyze collected social/community mention rows.")
    parser.add_argument("--all-history", action="store_true", help="Analyze every row in data/social_mentions.csv instead of the latest run only.")
    return analyze(parser.parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
