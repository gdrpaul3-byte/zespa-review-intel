#!/usr/bin/env python3
"""Low-rate public shopping search collector.

The collector only records data found in public search result HTML. If a source
blocks or returns an unsupported page, it records source status and emits no
fabricated product rows.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus, urlencode
from zoneinfo import ZoneInfo

import httpx
from bs4 import BeautifulSoup


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "search_terms.json"
DATA_DIR = ROOT / "data"
PRODUCTS_PATH = DATA_DIR / "products.csv"
STATUS_PATH = DATA_DIR / "source_status.json"

FIELDNAMES = [
    "collected_at_kst",
    "source",
    "brand",
    "query",
    "rank",
    "title",
    "url",
    "price",
    "rating",
    "review_count",
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
class ProductRow:
    collected_at_kst: str
    source: str
    brand: str
    query: str
    rank: int
    title: str
    url: str
    price: str
    rating: str
    review_count: str


def clean_text(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"\s+", " ", value).strip()


def digits(value: str | None) -> str:
    if not value:
        return ""
    found = re.findall(r"\d+", value.replace(",", ""))
    return "".join(found) if found else ""


def rating_text(value: str | None) -> str:
    if not value:
        return ""
    match = re.search(r"([0-5](?:\.\d+)?)", value)
    return match.group(1) if match else ""


def price_text(value: str | None) -> str:
    if not value:
        return ""
    if "원" not in value and not re.search(r"\d{2,}", value):
        return ""
    return digits(value)


def looks_blocked(status_code: int, html: str) -> bool:
    if status_code in {401, 403, 429, 503}:
        return True
    lowered = html[:6000].lower()
    blocked_markers = [
        "captcha",
        "access denied",
        "temporarily unavailable",
        "robot",
        "비정상",
        "자동화",
        "보안문자",
        "접근이 제한",
    ]
    return any(marker in lowered for marker in blocked_markers)


def load_config() -> dict[str, Any]:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def now_kst() -> str:
    return datetime.now(ZoneInfo("Asia/Seoul")).isoformat(timespec="seconds")


def fetch_http(url: str, timeout: float) -> tuple[int, str, str]:
    try:
        with httpx.Client(headers=HEADERS, timeout=timeout, follow_redirects=True) as client:
            response = client.get(url)
            return response.status_code, response.text, str(response.url)
    except httpx.HTTPError as exc:
        return 0, "", f"{type(exc).__name__}: {exc}"


async def fetch_playwright(url: str, timeout_ms: int) -> tuple[int, str, str]:
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(extra_http_headers=HEADERS)
        response = await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
        await page.wait_for_timeout(1500)
        html = await page.content()
        final_url = page.url
        status = response.status if response else 0
        await browser.close()
        return status, html, final_url


def naver_url(base_url: str, query: str, page: int) -> str:
    start = 1 + ((page - 1) * 40)
    return f"{base_url}?{urlencode({'query': query, 'pagingIndex': page, 'pagingSize': 40, 'productSet': 'total', 'sort': 'rel', 'viewType': 'list', 'frm': 'NVSHATC', 'origQuery': query})}&start={start}"


def coupang_url(base_url: str, query: str, page: int) -> str:
    return f"{base_url}?{urlencode({'q': query, 'channel': 'user', 'page': page})}"


def parse_json_ld(soup: BeautifulSoup) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            payload = json.loads(script.string or "")
        except json.JSONDecodeError:
            continue
        nodes = payload if isinstance(payload, list) else [payload]
        for node in nodes:
            if not isinstance(node, dict):
                continue
            items = node.get("itemListElement") or []
            for item in items if isinstance(items, list) else []:
                product = item.get("item", item) if isinstance(item, dict) else {}
                if not isinstance(product, dict):
                    continue
                name = clean_text(product.get("name"))
                if name:
                    rows.append(
                        {
                            "title": name,
                            "url": clean_text(product.get("url")),
                            "price": price_text(str(product.get("offers", {}).get("price", "")) if isinstance(product.get("offers"), dict) else ""),
                            "rating": rating_text(str(product.get("aggregateRating", {}).get("ratingValue", "")) if isinstance(product.get("aggregateRating"), dict) else ""),
                            "review_count": digits(str(product.get("aggregateRating", {}).get("reviewCount", "")) if isinstance(product.get("aggregateRating"), dict) else ""),
                        }
                    )
    return rows


def parse_naver(html: str, max_items: int) -> list[dict[str, str]]:
    soup = BeautifulSoup(html, "lxml")
    rows = parse_json_ld(soup)
    if rows:
        return rows[:max_items]

    cards = soup.select("[class*=product_item], [class*=basicList_item], li[class*=product]")
    parsed: list[dict[str, str]] = []
    for card in cards:
        link = card.select_one("a[class*=product_link], a[class*=basicList_link], a[href]")
        title = clean_text(link.get_text(" ", strip=True) if link else "")
        if not title or len(title) < 2:
            continue
        text = clean_text(card.get_text(" ", strip=True))
        price_el = card.select_one("[class*=price_num], [class*=price], em")
        rating_el = card.find(string=re.compile(r"(평점|별점)\s*[0-5]"))
        review_el = card.find(string=re.compile(r"(리뷰|상품평|구매건수)"))
        parsed.append(
            {
                "title": title,
                "url": link.get("href", "") if link else "",
                "price": price_text(price_el.get_text(" ", strip=True) if price_el else text),
                "rating": rating_text(str(rating_el) if rating_el else text),
                "review_count": digits(str(review_el) if review_el else ""),
            }
        )
        if len(parsed) >= max_items:
            break
    return parsed


def parse_coupang(html: str, max_items: int) -> list[dict[str, str]]:
    soup = BeautifulSoup(html, "lxml")
    rows = parse_json_ld(soup)
    if rows:
        return rows[:max_items]

    cards = soup.select("li.search-product, li[class*=search-product], .baby-product, [data-product-id]")
    parsed: list[dict[str, str]] = []
    for card in cards:
        title_el = card.select_one(".name, [class*=name], a")
        title = clean_text(title_el.get_text(" ", strip=True) if title_el else "")
        if not title or "광고" == title:
            continue
        link = card.select_one("a[href]")
        href = link.get("href", "") if link else ""
        if href.startswith("/"):
            href = "https://www.coupang.com" + href
        price_el = card.select_one(".price-value, [class*=price-value], strong")
        rating_el = card.select_one(".rating, [class*=rating]")
        review_el = card.select_one(".rating-total-count, [class*=rating-total-count]")
        text = clean_text(card.get_text(" ", strip=True))
        parsed.append(
            {
                "title": title,
                "url": href,
                "price": price_text(price_el.get_text(" ", strip=True) if price_el else text),
                "rating": rating_text(rating_el.get_text(" ", strip=True) if rating_el else text),
                "review_count": digits(review_el.get_text(" ", strip=True) if review_el else ""),
            }
        )
        if len(parsed) >= max_items:
            break
    return parsed


def build_url(source: str, base_url: str, query: str, page: int) -> str:
    if source == "naver_shopping":
        return naver_url(base_url, query, page)
    if source == "coupang":
        return coupang_url(base_url, query, page)
    raise ValueError(f"Unsupported source: {source}")


def parse_source(source: str, html: str, max_items: int) -> list[dict[str, str]]:
    if source == "naver_shopping":
        return parse_naver(html, max_items)
    if source == "coupang":
        return parse_coupang(html, max_items)
    return []


def append_products(rows: list[ProductRow]) -> None:
    DATA_DIR.mkdir(exist_ok=True)
    exists = PRODUCTS_PATH.exists()
    with PRODUCTS_PATH.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        if not exists:
            writer.writeheader()
        for row in rows:
            writer.writerow(asdict(row))


def write_status(status: list[dict[str, Any]]) -> None:
    DATA_DIR.mkdir(exist_ok=True)
    STATUS_PATH.write_text(
        json.dumps(
            {
                "updated_at_kst": now_kst(),
                "sources": status,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def collect(args: argparse.Namespace) -> int:
    config = load_config()
    rows: list[ProductRow] = []
    status: list[dict[str, Any]] = []
    collected_at = now_kst()

    for source, source_config in config["sources"].items():
        if not source_config.get("enabled", True):
            continue
        for brand, queries in config["brands"].items():
            for query in queries:
                for page in range(1, args.max_pages + 1):
                    url = build_url(source, source_config["base_url"], query, page)
                    status_code, html, final_url = fetch_http(url, args.timeout)
                    fetch_method = "httpx"
                    if args.playwright and (status_code == 0 or looks_blocked(status_code, html)):
                        try:
                            import asyncio

                            status_code, html, final_url = asyncio.run(fetch_playwright(url, int(args.timeout * 1000)))
                            fetch_method = "playwright"
                        except Exception as exc:  # noqa: BLE001
                            status_code, html, final_url = 0, "", f"PlaywrightError: {type(exc).__name__}: {exc}"

                    blocked = looks_blocked(status_code, html)
                    parsed = [] if blocked or status_code == 0 else parse_source(source, html, args.max_items)
                    for index, product in enumerate(parsed, start=1):
                        rows.append(
                            ProductRow(
                                collected_at_kst=collected_at,
                                source=source,
                                brand=brand,
                                query=query,
                                rank=index + ((page - 1) * args.max_items),
                                title=product.get("title", ""),
                                url=product.get("url", ""),
                                price=product.get("price", ""),
                                rating=product.get("rating", ""),
                                review_count=product.get("review_count", ""),
                            )
                        )

                    status.append(
                        {
                            "checked_at_kst": now_kst(),
                            "source": source,
                            "brand": brand,
                            "query": query,
                            "page": page,
                            "url": url,
                            "final_url": final_url,
                            "method": fetch_method,
                            "http_status": status_code,
                            "blocked": blocked,
                            "rows_found": len(parsed),
                            "error": "" if status_code and not blocked else ("blocked_or_challenge" if blocked else final_url),
                        }
                    )
                    time.sleep(args.delay)

    append_products(rows)
    write_status(status)
    print(f"Collected {len(rows)} product rows; wrote {STATUS_PATH.relative_to(ROOT)}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect public product cards from shopping search pages.")
    parser.add_argument("--max-pages", type=int, default=1, help="Pages per query per source.")
    parser.add_argument("--max-items", type=int, default=20, help="Max items parsed per page.")
    parser.add_argument("--delay", type=float, default=None, help="Delay between requests in seconds.")
    parser.add_argument("--timeout", type=float, default=20.0, help="HTTP timeout in seconds.")
    parser.add_argument("--playwright", action="store_true", help="Try Playwright when httpx appears blocked.")
    args = parser.parse_args()

    config = load_config()
    if args.delay is None:
        args.delay = float(config.get("request_delay_seconds", 2.0))
    return collect(args)


if __name__ == "__main__":
    raise SystemExit(main())
