#!/usr/bin/env python3
"""Collect low-rate public social/community mentions.

Only no-login public surfaces are attempted: Daum search HTML, Jina Reader
fallbacks for search/result pages, optional yt-dlp YouTube search, optional rdt
Reddit search, and configured RSS feeds. Blocked or unsupported sources are
recorded in status and do not produce fabricated rows.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import shutil
import subprocess
import time
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass
from datetime import datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlencode, urljoin, urlparse
from zoneinfo import ZoneInfo

import httpx
from bs4 import BeautifulSoup


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "social_sources.json"
DATA_DIR = ROOT / "data"
MENTIONS_PATH = DATA_DIR / "social_mentions.csv"
STATUS_PATH = DATA_DIR / "social_source_status.json"

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

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.7,en;q=0.6",
}


@dataclass
class SocialRow:
    collected_at_kst: str
    platform: str
    source_name: str
    source_method: str
    brand: str
    query: str
    title: str
    snippet: str
    url: str
    author: str
    published_at: str
    engagement_score: str
    sentiment: str
    mention_type: str
    product_cluster: str
    raw_status: str


def clean_text(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"\s+", " ", value).strip()


def now_kst() -> str:
    return datetime.now(ZoneInfo("Asia/Seoul")).isoformat(timespec="seconds")


def load_config() -> dict[str, Any]:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def looks_blocked(status_code: int, text: str) -> bool:
    if status_code in {401, 403, 429, 503}:
        return True
    lowered = text[:7000].lower()
    markers = [
        "captcha",
        "access denied",
        "robot",
        "automated",
        "비정상",
        "자동화",
        "보안문자",
        "접근이 제한",
        "too many requests",
    ]
    return any(marker in lowered for marker in markers)


def fetch_http(url: str, timeout: float) -> tuple[int, str, str]:
    try:
        with httpx.Client(headers=HEADERS, timeout=timeout, follow_redirects=True) as client:
            response = client.get(url)
            return response.status_code, response.text, str(response.url)
    except httpx.HTTPError as exc:
        return 0, "", f"{type(exc).__name__}: {exc}"


def daum_search_url(base_url: str, query: str, page: int) -> str:
    params = {"w": "tot", "q": query}
    if page > 1:
        params["page"] = str(page)
    return f"{base_url}?{urlencode(params)}"


def jina_reader_url(url: str) -> str:
    return "https://r.jina.ai/" + quote(url, safe=":/?&=%")


def infer_platform(url: str, fallback: str) -> str:
    host = urlparse(url).netloc.lower()
    mapping = [
        ("youtube.com", "youtube"),
        ("youtu.be", "youtube"),
        ("reddit.com", "reddit"),
        ("instagram.com", "instagram"),
        ("threads.net", "threads"),
        ("cafe.naver.com", "naver_cafe"),
        ("dcinside.com", "dcinside"),
        ("ppomppu.co.kr", "ppomppu"),
        ("clien.net", "clien"),
        ("theqoo.net", "theqoo"),
        ("daum.net", "daum"),
    ]
    for marker, platform in mapping:
        if marker in host:
            return platform
    return fallback


def infer_brand(query: str, configured_brand: str) -> str:
    text = query.lower()
    if "제스파" in query or "zespa" in text:
        return "Zespa"
    if "바디프렌드" in query or "바디프랜드" in query or "bodyfriend" in text:
        return "Bodyfriend"
    return configured_brand


def parse_daum_results(html: str, max_items: int, fallback_platform: str) -> list[dict[str, str]]:
    soup = BeautifulSoup(html, "lxml")
    parsed: list[dict[str, str]] = []
    seen: set[str] = set()
    selectors = [
        ".c-list-basic li",
        ".list_news li",
        ".list_info li",
        ".cont_inner",
        ".wrap_cont",
        "li",
    ]
    cards = []
    for selector in selectors:
        cards = soup.select(selector)
        if cards:
            break
    for card in cards:
        link = card.select_one("a[href]")
        if not link:
            continue
        href = urljoin("https://search.daum.net", link.get("href", ""))
        title = clean_text(link.get_text(" ", strip=True))
        if not title or len(title) < 2:
            continue
        host = urlparse(href).netloc.lower()
        if "search.daum.net" in host and "q=" in href:
            continue
        if href in seen:
            continue
        seen.add(href)
        body = clean_text(card.get_text(" ", strip=True))
        snippet = body.replace(title, "", 1).strip(" -|")
        parsed.append(
            {
                "platform": infer_platform(href, fallback_platform),
                "title": title,
                "snippet": snippet[:500],
                "url": href,
                "author": "",
                "published_at": "",
                "engagement_score": "",
            }
        )
        if len(parsed) >= max_items:
            break
    return parsed


def parse_jina_results(markdown: str, max_items: int, fallback_platform: str) -> list[dict[str, str]]:
    parsed: list[dict[str, str]] = []
    seen: set[str] = set()
    lines = [clean_text(line) for line in markdown.splitlines()]
    for index, line in enumerate(lines):
        for title, href in re.findall(r"\[([^\]]{2,180})\]\((https?://[^)]+)\)", line):
            if href in seen or "r.jina.ai" in urlparse(href).netloc:
                continue
            seen.add(href)
            snippet = ""
            for neighbor in lines[index + 1 : index + 4]:
                if neighbor and not neighbor.startswith("[") and "http://" not in neighbor and "https://" not in neighbor:
                    snippet = neighbor[:500]
                    break
            parsed.append(
                {
                    "platform": infer_platform(href, fallback_platform),
                    "title": clean_text(title),
                    "snippet": snippet,
                    "url": href,
                    "author": "",
                    "published_at": "",
                    "engagement_score": "",
                }
            )
            if len(parsed) >= max_items:
                return parsed
    return parsed


def parse_rss_datetime(value: str) -> str:
    if not value:
        return ""
    try:
        return parsedate_to_datetime(value).isoformat()
    except (TypeError, ValueError, IndexError, OverflowError):
        return clean_text(value)


def parse_rss(text: str, max_items: int) -> list[dict[str, str]]:
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return []
    ns = {
        "atom": "http://www.w3.org/2005/Atom",
        "dc": "http://purl.org/dc/elements/1.1/",
    }
    rows: list[dict[str, str]] = []
    rss_items = root.findall(".//item")
    atom_items = root.findall(".//atom:entry", ns)
    for item in rss_items:
        title = clean_text(item.findtext("title"))
        link = clean_text(item.findtext("link"))
        snippet = clean_text(item.findtext("description"))
        author = clean_text(item.findtext("author") or item.findtext("dc:creator", namespaces=ns))
        published = parse_rss_datetime(item.findtext("pubDate") or "")
        if title and link:
            rows.append({"platform": infer_platform(link, "rss"), "title": title, "snippet": snippet, "url": link, "author": author, "published_at": published, "engagement_score": ""})
        if len(rows) >= max_items:
            return rows
    for item in atom_items:
        title = clean_text(item.findtext("atom:title", namespaces=ns))
        link_el = item.find("atom:link", ns)
        link = clean_text(link_el.get("href", "") if link_el is not None else "")
        snippet = clean_text(item.findtext("atom:summary", namespaces=ns) or item.findtext("atom:content", namespaces=ns))
        author = clean_text(item.findtext("atom:author/atom:name", namespaces=ns))
        published = clean_text(item.findtext("atom:published", namespaces=ns) or item.findtext("atom:updated", namespaces=ns))
        if title and link:
            rows.append({"platform": infer_platform(link, "rss"), "title": title, "snippet": snippet, "url": link, "author": author, "published_at": published, "engagement_score": ""})
        if len(rows) >= max_items:
            return rows
    return rows


def run_yt_dlp(query: str, max_items: int, timeout: float) -> tuple[list[dict[str, str]], str]:
    if not shutil.which("yt-dlp"):
        return [], "yt-dlp_not_installed"
    command = [
        "yt-dlp",
        "--ignore-config",
        "--skip-download",
        "--dump-json",
        "--no-warnings",
        f"ytsearch{max_items}:{query}",
    ]
    try:
        completed = subprocess.run(command, check=False, capture_output=True, text=True, timeout=timeout)
    except (subprocess.SubprocessError, OSError) as exc:
        return [], f"{type(exc).__name__}: {exc}"
    rows = []
    for line in completed.stdout.splitlines():
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        title = clean_text(item.get("title"))
        video_id = clean_text(item.get("id"))
        if not title or not video_id:
            continue
        rows.append(
            {
                "platform": "youtube",
                "title": title,
                "snippet": clean_text(item.get("description") or ""),
                "url": clean_text(item.get("webpage_url") or f"https://www.youtube.com/watch?v={video_id}"),
                "author": clean_text(item.get("channel") or item.get("uploader") or ""),
                "published_at": clean_text(str(item.get("upload_date") or "")),
                "engagement_score": str(int(item.get("view_count") or 0)) if item.get("view_count") is not None else "",
            }
        )
        if len(rows) >= max_items:
            break
    error = clean_text(completed.stderr)
    if completed.returncode != 0 and not rows:
        return [], error or f"yt-dlp_exit_{completed.returncode}"
    return rows, error


def run_rdt(query: str, max_items: int, timeout: float) -> tuple[list[dict[str, str]], str]:
    if not shutil.which("rdt"):
        return [], "rdt_not_installed"
    attempts = [
        ["rdt", "export", "search", query, "--format", "json", "--limit", str(max_items)],
        ["rdt", "search", query, "--json", "--limit", str(max_items)],
    ]
    last_error = ""
    for command in attempts:
        try:
            completed = subprocess.run(command, check=False, capture_output=True, text=True, timeout=timeout)
        except (subprocess.SubprocessError, OSError) as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            continue
        payload = completed.stdout.strip()
        rows = parse_rdt_payload(payload, max_items)
        if rows:
            return rows, clean_text(completed.stderr)
        last_error = clean_text(completed.stderr) or f"rdt_exit_{completed.returncode}"
    return [], last_error


def parse_rdt_payload(payload: str, max_items: int) -> list[dict[str, str]]:
    if not payload:
        return []
    objects: list[Any] = []
    try:
        data = json.loads(payload)
        objects = data if isinstance(data, list) else data.get("results", data.get("posts", [])) if isinstance(data, dict) else []
    except json.JSONDecodeError:
        for line in payload.splitlines():
            try:
                objects.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    rows = []
    for item in objects:
        if not isinstance(item, dict):
            continue
        title = clean_text(item.get("title") or item.get("name"))
        permalink = clean_text(item.get("permalink") or item.get("url"))
        if permalink.startswith("/"):
            permalink = "https://www.reddit.com" + permalink
        if title and permalink:
            score = item.get("score") or item.get("ups") or item.get("comments") or ""
            rows.append(
                {
                    "platform": "reddit",
                    "title": title,
                    "snippet": clean_text(item.get("selftext") or item.get("text") or item.get("snippet") or ""),
                    "url": permalink,
                    "author": clean_text(item.get("author") or item.get("subreddit") or ""),
                    "published_at": clean_text(str(item.get("created_utc") or item.get("created") or "")),
                    "engagement_score": str(score) if score != "" else "",
                }
            )
        if len(rows) >= max_items:
            break
    return rows


def append_mentions(rows: list[SocialRow], dry_run: bool) -> None:
    if dry_run:
        return
    DATA_DIR.mkdir(exist_ok=True)
    exists = MENTIONS_PATH.exists()
    with MENTIONS_PATH.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        if not exists:
            writer.writeheader()
        for row in rows:
            writer.writerow(asdict(row))


def write_status(status: list[dict[str, Any]]) -> None:
    DATA_DIR.mkdir(exist_ok=True)
    STATUS_PATH.write_text(json.dumps({"updated_at_kst": now_kst(), "sources": status}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def row_from_item(collected_at: str, item: dict[str, str], source_name: str, method: str, brand: str, query: str, raw_status: str) -> SocialRow:
    return SocialRow(
        collected_at_kst=collected_at,
        platform=item.get("platform", source_name),
        source_name=source_name,
        source_method=method,
        brand=infer_brand(query, brand),
        query=query,
        title=item.get("title", ""),
        snippet=item.get("snippet", ""),
        url=item.get("url", ""),
        author=item.get("author", ""),
        published_at=item.get("published_at", ""),
        engagement_score=item.get("engagement_score", ""),
        sentiment="",
        mention_type="",
        product_cluster="",
        raw_status=raw_status,
    )


def collect_search_source(args: argparse.Namespace, config: dict[str, Any], source_name: str, method: str, collected_at: str) -> tuple[list[SocialRow], list[dict[str, Any]]]:
    source_config = config["sources"][source_name]
    rows: list[SocialRow] = []
    status: list[dict[str, Any]] = []
    for brand, queries in config["brands"].items():
        for query in queries:
            for page in range(1, args.max_pages + 1):
                search_url = daum_search_url(source_config["base_url"], query, page)
                url = jina_reader_url(search_url) if method == "jina_reader" else search_url
                status_code, text, final_url = fetch_http(url, args.timeout)
                blocked = looks_blocked(status_code, text)
                parsed = []
                if status_code and not blocked:
                    parsed = parse_jina_results(text, args.max_items, "search") if method == "jina_reader" else parse_daum_results(text, args.max_items, "search")
                for item in parsed:
                    rows.append(row_from_item(collected_at, item, source_name, method, brand, query, "ok"))
                status.append(
                    {
                        "checked_at_kst": now_kst(),
                        "source": source_name,
                        "method": method,
                        "brand": brand,
                        "query": query,
                        "page": page,
                        "url": search_url,
                        "final_url": final_url,
                        "http_status": status_code,
                        "blocked": blocked,
                        "rows_found": len(parsed),
                        "error": "" if status_code and not blocked else ("blocked_or_challenge" if blocked else final_url),
                    }
                )
                time.sleep(args.delay)
    return rows, status


def collect_site_search(args: argparse.Namespace, config: dict[str, Any], collected_at: str) -> tuple[list[SocialRow], list[dict[str, Any]]]:
    base_url = config["sources"]["daum_search"]["base_url"]
    rows: list[SocialRow] = []
    status: list[dict[str, Any]] = []
    for site_config in config.get("site_search", []):
        platform = site_config["platform"]
        site = site_config["site"]
        for query_seed in site_config.get("queries", []):
            query = f"site:{site} {query_seed}"
            search_url = daum_search_url(base_url, query, 1)
            for method, url in (("daum_site_search", search_url), ("jina_site_search", jina_reader_url(search_url))):
                status_code, text, final_url = fetch_http(url, args.timeout)
                blocked = looks_blocked(status_code, text)
                parsed = []
                if status_code and not blocked:
                    parser = parse_jina_results if method == "jina_site_search" else parse_daum_results
                    parsed = parser(text, args.max_items, platform)
                for item in parsed:
                    item["platform"] = platform
                    rows.append(row_from_item(collected_at, item, "site_search", method, infer_brand(query_seed, "Category"), query, "ok"))
                status.append(
                    {
                        "checked_at_kst": now_kst(),
                        "source": "site_search",
                        "method": method,
                        "platform": platform,
                        "query": query,
                        "page": 1,
                        "url": search_url,
                        "final_url": final_url,
                        "http_status": status_code,
                        "blocked": blocked,
                        "rows_found": len(parsed),
                        "error": "" if status_code and not blocked else ("blocked_or_challenge" if blocked else final_url),
                    }
                )
                time.sleep(args.delay)
    return rows, status


def collect_cli_source(args: argparse.Namespace, config: dict[str, Any], source_name: str, collected_at: str) -> tuple[list[SocialRow], list[dict[str, Any]]]:
    rows: list[SocialRow] = []
    status: list[dict[str, Any]] = []
    source_config = config["sources"][source_name]
    method = source_config["method"]
    for query in source_config.get("queries", []):
        if method == "yt_dlp":
            parsed, error = run_yt_dlp(query, args.max_items, args.timeout)
        elif method == "rdt":
            parsed, error = run_rdt(query, args.max_items, args.timeout)
        else:
            parsed, error = [], "unsupported_cli_method"
        for item in parsed:
            rows.append(row_from_item(collected_at, item, source_name, method, infer_brand(query, "Category"), query, "ok"))
        status.append(
            {
                "checked_at_kst": now_kst(),
                "source": source_name,
                "method": method,
                "query": query,
                "http_status": "",
                "blocked": False,
                "rows_found": len(parsed),
                "error": error if not parsed else "",
            }
        )
        time.sleep(args.delay)
    return rows, status


def collect_rss(args: argparse.Namespace, config: dict[str, Any], collected_at: str) -> tuple[list[SocialRow], list[dict[str, Any]]]:
    rows: list[SocialRow] = []
    status: list[dict[str, Any]] = []
    for feed in config["sources"].get("rss", {}).get("feeds", []):
        url = feed.get("url", "")
        name = feed.get("name", url)
        if not url:
            continue
        status_code, text, final_url = fetch_http(url, args.timeout)
        blocked = looks_blocked(status_code, text)
        parsed = parse_rss(text, args.max_items) if status_code and not blocked else []
        query = feed.get("query", name)
        brand = infer_brand(query, feed.get("brand", "Category"))
        for item in parsed:
            rows.append(row_from_item(collected_at, item, name, "rss", brand, query, "ok"))
        status.append(
            {
                "checked_at_kst": now_kst(),
                "source": name,
                "method": "rss",
                "query": query,
                "url": url,
                "final_url": final_url,
                "http_status": status_code,
                "blocked": blocked,
                "rows_found": len(parsed),
                "error": "" if status_code and not blocked else ("blocked_or_challenge" if blocked else final_url),
            }
        )
        time.sleep(args.delay)
    return rows, status


def dedupe_rows(rows: list[SocialRow]) -> list[SocialRow]:
    deduped: list[SocialRow] = []
    seen: set[tuple[str, str, str]] = set()
    for row in rows:
        key = (row.url, row.title, row.query)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(row)
    return deduped


def collect(args: argparse.Namespace) -> int:
    config = load_config()
    collected_at = now_kst()
    all_rows: list[SocialRow] = []
    all_status: list[dict[str, Any]] = []

    for source_name, source_config in config.get("sources", {}).items():
        if not source_config.get("enabled", True):
            continue
        method = source_config.get("method", "")
        if source_name in {"daum_search", "jina_daum_search"}:
            rows, status = collect_search_source(args, config, source_name, method, collected_at)
        elif method in {"yt_dlp", "rdt"}:
            rows, status = collect_cli_source(args, config, source_name, collected_at)
        elif method == "rss":
            rows, status = collect_rss(args, config, collected_at)
        else:
            rows, status = [], []
        all_rows.extend(rows)
        all_status.extend(status)

    site_rows, site_status = collect_site_search(args, config, collected_at)
    all_rows.extend(site_rows)
    all_status.extend(site_status)

    deduped = dedupe_rows(all_rows)
    append_mentions(deduped, args.dry_run)
    write_status(all_status)
    action = "Dry-run collected" if args.dry_run else "Collected"
    print(f"{action} {len(deduped)} social rows; wrote {STATUS_PATH.relative_to(ROOT)}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect public social/community mention rows.")
    parser.add_argument("--max-pages", type=int, default=1, help="Search pages per query.")
    parser.add_argument("--max-items", type=int, default=10, help="Max rows per source query.")
    parser.add_argument("--delay", type=float, default=None, help="Delay between source attempts.")
    parser.add_argument("--timeout", type=float, default=20.0, help="HTTP/CLI timeout in seconds.")
    parser.add_argument("--dry-run", action="store_true", help="Do not append data/social_mentions.csv.")
    args = parser.parse_args()

    config = load_config()
    if args.delay is None:
        args.delay = float(config.get("request_delay_seconds", 2.0))
    return collect(args)


if __name__ == "__main__":
    raise SystemExit(main())
