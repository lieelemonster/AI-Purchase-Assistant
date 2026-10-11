"""五个品类各抽 2 个型号，检查太平洋产品库能否搜到、读到参数和参考价。

用法：python -m app.scripts.pconline_survey
"""

import asyncio
import sys

from app.adapters.catalog.pconline import CATEGORY_DIRS, CatalogSearchError, PconlineCatalog
from app.adapters.pages.reader import PageReader
from app.config.field_tables import load_field_table
from app.config.settings import load_runtime_config
from app.core.verification.price_parsing import parse_reference_price
from app.core.verification.spec_parsing import parse_spec_page

SAMPLES = [
    ("笔记本电脑", "laptop", "华为MateBook 14"),
    ("笔记本电脑", "laptop", "联想小新"),
    ("手机", "phone", "华为Mate 70"),
    ("手机", "phone", "小米15"),
    ("平板电脑", "tablet", "苹果iPad Air"),
    ("平板电脑", "tablet", "华为MatePad"),
    ("显示器", "monitor", "戴尔U2724D"),
    ("显示器", "monitor", "小米显示器"),
    ("耳机", "headphones", "索尼WH-1000XM5"),
    ("耳机", "headphones", "华为FreeBuds"),
]
PAUSE_S = 4


async def main() -> int:
    config = load_runtime_config()
    reader = PageReader(max_page_bytes=config.max_page_bytes, timeout_s=config.call_timeout_s)
    catalog = PconlineCatalog(reader)
    print("品类\t关键词\t名称\t网址\t参数字段数\t参考价\t停产\t说明")
    fact_counter = 0

    def next_fact_id():
        nonlocal fact_counter
        fact_counter += 1
        return f"f{fact_counter}"

    for label, category_id, keyword in SAMPLES:
        await asyncio.sleep(PAUSE_S)
        try:
            hits = await catalog.search(keyword)
        except CatalogSearchError as exc:
            print(f"{label}\t{keyword}\t\t\t\t\t\t搜索失败：{exc.reason}")
            continue
        allowed = set(CATEGORY_DIRS[category_id])
        chosen = next((hit for hit in hits if hit.category_dir in allowed and not hit.discontinued), None)
        if chosen is None:
            print(f"{label}\t{keyword}\t\t\t0\t无\t\t搜索有 {len(hits)} 条，没有未停产的本品类结果")
            continue
        await asyncio.sleep(PAUSE_S)
        detail = await reader.read(chosen.detail_url, "e1")
        await asyncio.sleep(PAUSE_S)
        price_doc = await reader.read(chosen.price_url, "e2")
        parsed = parse_spec_page(detail, load_field_table(category_id), "c1", next_fact_id)
        supported = sum(1 for fact in parsed.facts if fact.status == "supported")
        price = parse_reference_price(price_doc, "c1", chosen.name, multi_config=False)
        amount = "无" if price.amount_minor is None else f"{price.amount_minor / 100:.0f}"
        note = []
        if parsed.status != "ok":
            note.append(f"参数页：{parsed.reason}")
        if price.status != "supported":
            note.append("报价页没有参考价（行货价格）")
        if detail.fetch_status != "ok":
            note.append(f"参数页读取失败：{detail.failure_reason}")
        if price_doc.fetch_status != "ok":
            note.append(f"报价页读取失败：{price_doc.failure_reason}")
        print("\t".join([
            label, keyword, chosen.name, chosen.url, str(supported), amount,
            "是" if chosen.discontinued else "否", "；".join(note),
        ]))
    print("目录 " + ", ".join(f"{key}={','.join(value)}" for key, value in CATEGORY_DIRS.items()))
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
