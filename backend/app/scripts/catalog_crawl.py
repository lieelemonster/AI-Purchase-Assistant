"""从太平洋产品库 sitemap 抓取五个品类的近期产品，写入本地 SQLite。

只访问 product.pconline.com.cn 上 robots.txt 允许的产品首页和参数页。
不访问 ks.pconline.com.cn（该站 Disallow: /）。请求间隔使用运行配置，目前是 3 秒。
"""

import asyncio
import json
import re
import sqlite3
import xml.etree.ElementTree as ET
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import urljoin, urlparse, urlunparse

import httpx

from app.adapters.pages.reader import PageReader
from app.config.settings import load_runtime_config
from app.core.verification.price_parsing import HOME_PRICE

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = ROOT / "data" / "catalog.sqlite"
SITEMAP_HOST = "product.pconline.com.cn"
SITEMAP_INDEX = f"https://{SITEMAP_HOST}/seo_xml/soso_xml/product_sitemap_index.xml"
NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
# 2026-10-11 起算，近两年。
CUTOFF = date(2024, 10, 11)
HOME_URL = re.compile(
    r"^https?://product\.pconline\.com\.cn/(notebook|mobile|tabletpc|lcd|earphone)/([a-z0-9_]+)/(\d+)\.html$"
)
DATE_TEXT = re.compile(r"(20\d{2})\s*年(?:\s*(\d{1,2})\s*月)?(?:\s*(\d{1,2})\s*日)?")

# 目录名来自太平洋产品库网址，对应《中国电商官方渠道汇总》里这五个品类的品牌。
CATEGORY_BY_DIR = {
    "notebook": "laptop",
    "mobile": "phone",
    "tabletpc": "tablet",
    "lcd": "monitor",
    "earphone": "headphones",
}
BRAND_DIRS = {
    "notebook": {
        "lenovo", "apple", "huawei", "asus", "acer", "hp", "dell", "honor", "gigabyte",
        "mechrevo", "hasee", "thunderobot", "colorful", "machenike", "microsoft", "vaio",
    },
    "mobile": {
        "apple", "huawei", "xiaomi", "redmi", "oppo", "vivo", "iqoo", "samsung", "honor",
        "oneplus", "realme", "meizu", "nubia", "zte", "motorola", "asus",
    },
    "tabletpc": {
        "apple", "huawei", "xiaomi", "redmi", "lenovo", "samsung", "honor", "oppo", "vivo",
        "iqoo", "realme", "microsoft", "teclast", "cube", "nubia", "zte",
    },
    "lcd": {
        "aoc", "lg", "samsung", "viewsonic", "asus", "acer", "xiaomi", "ktc", "hp", "hkc",
        "dell", "machenike", "titanarmy", "lenovo", "antgamer", "thunderobot",
    },
    "earphone": {
        "beats", "bose", "jbl", "1more", "samsung", "huawei", "soundcore", "xiaomi",
        "beyerdynamic", "sennheiser", "edifier", "akg", "sony", "logitech", "apple",
        "audio-technica", "audiotechnica", "shokz",
    },
}


def parse_release(text: str) -> Tuple[bool, Optional[str]]:
    """从参数页判断是否在近两年内发布。只有年份、看不出月份的 2024 年不算。"""
    matched = None
    for label in ("上市时间", "发布时间"):
        found = re.search(rf"{label}\s*\|\s*([^\n]+)", text)
        if found:
            matched = found.group(1)
            break
    if not matched:
        return False, None
    parsed = DATE_TEXT.search(matched)
    if parsed is None:
        return False, None
    year = int(parsed.group(1))
    month = parsed.group(2)
    day = parsed.group(3)
    if month is None:
        if year >= 2025:
            return True, f"{year}"
        return False, f"{year}"
    try:
        released = date(year, int(month), int(day) if day else 1)
    except ValueError:
        return False, None
    return released >= CUTOFF, released.isoformat()


def spec_rows(text: str) -> Dict[str, str]:
    rows = {}
    for line in text.splitlines():
        if " | " not in line:
            continue
        label, value = line.split(" | ", 1)
        label, value = label.strip(), " ".join(value.split()).strip()
        if label and value and label not in rows:
            rows[label] = value
    return rows


def price_yuan(text: str) -> Optional[int]:
    matched = HOME_PRICE.search(text)
    if matched is None:
        return None
    return int(matched.group(1).replace(",", "").split(".")[0])


def list_product_urls(xml_bytes: bytes) -> List[Tuple[str, str, str, str]]:
    root = ET.fromstring(xml_bytes)
    found = []
    for loc in root.findall(".//sm:loc", NS):
        if loc.text is None:
            continue
        url = loc.text.strip().replace("http://", "https://")
        matched = HOME_URL.match(url)
        if matched is None:
            continue
        category_dir, brand_dir, product_id = matched.groups()
        if brand_dir not in BRAND_DIRS[category_dir]:
            continue
        found.append((product_id, CATEGORY_BY_DIR[category_dir], brand_dir, url))
    return found


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB_PATH)
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS products (
            product_id TEXT PRIMARY KEY,
            category TEXT NOT NULL,
            brand_dir TEXT NOT NULL,
            name TEXT,
            url TEXT NOT NULL,
            release_date TEXT,
            price_yuan INTEGER,
            specs_json TEXT NOT NULL,
            fetched_at TEXT NOT NULL
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS crawl_log (
            url TEXT PRIMARY KEY,
            status TEXT NOT NULL,
            note TEXT,
            fetched_at TEXT NOT NULL
        )
        """
    )
    db.commit()
    return db


def already_done(db: sqlite3.Connection, url: str) -> bool:
    row = db.execute("SELECT 1 FROM crawl_log WHERE url = ?", (url,)).fetchone()
    return row is not None


def remember(db: sqlite3.Connection, url: str, status: str, note: str = "") -> None:
    db.execute(
        "INSERT OR REPLACE INTO crawl_log (url, status, note, fetched_at) VALUES (?, ?, ?, ?)",
        (url, status, note, datetime.now(timezone.utc).isoformat()),
    )
    db.commit()


def product_sitemap_url(url: str) -> Optional[str]:
    """只保留 product.pconline.com.cn，并改用 https。不跟随到其它站点。"""
    parsed = urlparse(url.strip())
    if (parsed.hostname or "").lower() != SITEMAP_HOST:
        return None
    return urlunparse(parsed._replace(scheme="https"))


async def sitemap_bytes(client: httpx.AsyncClient, url: str) -> bytes:
    target = product_sitemap_url(url)
    if target is None:
        raise ValueError(f"拒绝非产品库地址 {url}")
    last_error: Optional[BaseException] = None
    for _ in range(3):
        try:
            response = await client.get(target, timeout=30, follow_redirects=False)
            if response.status_code in {301, 302, 303, 307, 308}:
                location = urljoin(target, response.headers.get("location", ""))
                nxt = product_sitemap_url(location)
                if nxt is None or nxt == target:
                    raise ValueError(f"拒绝跳转到非产品库地址 {location}")
                response = await client.get(nxt, timeout=30, follow_redirects=False)
            response.raise_for_status()
            return response.content
        except (httpx.TransportError, httpx.TimeoutException) as exc:
            last_error = exc
            print(f"sitemap 连接失败，按原间隔重试 {target}", flush=True)
            await asyncio.sleep(load_runtime_config().source_min_interval_s)
    raise last_error  # type: ignore[misc]


async def collect_targets(client: httpx.AsyncClient) -> List[Tuple[str, str, str, str]]:
    index = ET.fromstring(await sitemap_bytes(client, SITEMAP_INDEX))
    targets = []
    seen = set()
    for loc in index.findall(".//sm:loc", NS):
        if loc.text is None or "product_sitemap_" not in loc.text:
            continue
        child = product_sitemap_url(loc.text)
        if child is None:
            print(f"跳过非产品库 sitemap {loc.text.strip()}", flush=True)
            continue
        for item in list_product_urls(await sitemap_bytes(client, child)):
            if item[0] in seen:
                continue
            seen.add(item[0])
            targets.append(item)
        await asyncio.sleep(load_runtime_config().source_min_interval_s)
    return targets


async def crawl() -> None:
    config = load_runtime_config()
    reader = PageReader(max_page_bytes=config.max_page_bytes, timeout_s=config.call_timeout_s, retry_wait_s=8)
    db = connect()
    async with httpx.AsyncClient(headers={"User-Agent": "AIBuyAssistant/0.1 (+official product page reader)"}) as client:
        targets = await collect_targets(client)
    print(f"候选产品首页 {len(targets)} 个", flush=True)
    kept = 0
    for product_id, category, brand_dir, url in targets:
        if already_done(db, url):
            continue
        await asyncio.sleep(config.source_min_interval_s)
        home = await reader.read(url, "e1")
        if home.fetch_status != "ok":
            remember(db, url, "home_failed", home.failure_reason or "")
            print(f"首页失败 {url} {home.failure_reason}", flush=True)
            continue
        await asyncio.sleep(config.source_min_interval_s)
        detail_url = url[: -len(".html")] + "_detail.html"
        detail = await reader.read(detail_url, "e2")
        if detail.fetch_status != "ok":
            remember(db, url, "detail_failed", detail.failure_reason or "")
            print(f"参数页失败 {detail_url} {detail.failure_reason}", flush=True)
            continue
        recent, released = parse_release(detail.text)
        if not recent:
            remember(db, url, "too_old", released or "")
            continue
        amount = price_yuan(home.text)
        specs = spec_rows(detail.text)
        db.execute(
            """
            INSERT OR REPLACE INTO products
            (product_id, category, brand_dir, name, url, release_date, price_yuan, specs_json, fetched_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                product_id,
                category,
                brand_dir,
                home.title,
                url,
                released,
                amount,
                json.dumps(specs, ensure_ascii=False),
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        remember(db, url, "stored", released or "")
        kept += 1
        print(f"入库 {category} {brand_dir} {product_id} 价格={amount} 发布={released}", flush=True)
    total = db.execute("SELECT COUNT(*) FROM products").fetchone()[0]
    print(f"本次新入库 {kept}，库内共 {total}", flush=True)


def main() -> None:
    asyncio.run(crawl())


if __name__ == "__main__":
    main()
