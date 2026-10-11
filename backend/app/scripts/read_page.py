"""手动检查网页读取效果：python -m app.scripts.read_page <URL>"""

import asyncio
import sys

from app.adapters.pages.reader import PageReader
from app.config.settings import load_runtime_config


async def main(url: str) -> int:
    config = load_runtime_config()
    reader = PageReader(max_page_bytes=config.max_page_bytes, timeout_s=config.call_timeout_s)
    doc = await reader.read(url, evidence_id="e1")
    print(f"读取状态：{doc.fetch_status}")
    if doc.fetch_status != "ok":
        print(f"失败原因：{doc.failure_reason}")
        return 1
    print(f"最终 URL：{doc.final_url}")
    print(f"页面标题：{doc.title}")
    print(f"访问时间：{doc.fetched_at.isoformat()}")
    print(f"内容哈希：{doc.content_hash}")
    print(f"正文长度：{len(doc.text)} 字")
    print("正文前 500 字：")
    print(doc.text[:500])
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("用法：python -m app.scripts.read_page <URL>")
        sys.exit(2)
    sys.exit(asyncio.run(main(sys.argv[1])))
