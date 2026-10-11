"""手动检查太平洋站内搜索：python -m app.scripts.pconline_search <关键词>"""

import asyncio
import sys

from app.adapters.catalog.pconline import CatalogSearchError, PconlineCatalog, build_search_url
from app.adapters.pages.reader import PageReader
from app.config.settings import load_runtime_config


async def main(keyword: str) -> int:
    config = load_runtime_config()
    catalog = PconlineCatalog(PageReader(max_page_bytes=config.max_page_bytes, timeout_s=config.call_timeout_s))
    print(f"搜索地址：{build_search_url(keyword)}")
    try:
        hits = await catalog.search(keyword)
    except CatalogSearchError as e:
        print(f"搜索失败：{e.reason}")
        return 1
    print(f"共 {len(hits)} 条结果")
    for hit in hits:
        flag = "【停产】" if hit.discontinued else ""
        print(f"- {flag}{hit.name}  {hit.url}")
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法：python -m app.scripts.pconline_search <关键词>")
        sys.exit(2)
    sys.exit(asyncio.run(main(" ".join(sys.argv[1:]))))
