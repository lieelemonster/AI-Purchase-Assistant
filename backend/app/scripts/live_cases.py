"""跑真实推荐并把精简结果打成 JSON。用法：python -m app.scripts.live_cases laptop|all|errors"""

import asyncio
import json
import sys
from contextlib import redirect_stdout
from io import StringIO

from app.adapters.catalog.pconline import CatalogSearchError, PconlineCatalog
from app.adapters.model.deepseek import DeepSeekGateway
from app.adapters.pages.reader import PageReader
from app.config.settings import load_project_env, load_runtime_config, load_secrets
from app.core.recommendation.recommend import RecommendRequest, recommend
from app.core.verification.catalog_evidence import Throttle, ThrottledReader
from app.schemas.need import OptionAnswer

LAPTOP = [
    ("写文档、预算没想好", "laptop", [OptionAnswer(question_id="usage", option_ids=["office"])], "我想买笔记本，主要写文档，预算还没想好", 1),
    ("剪视频、预算1万以内", "laptop", [OptionAnswer(question_id="usage", option_ids=["creative"])], "主要剪视频，预算1万以内", 1),
    ("经常出差、要轻", "laptop", [OptionAnswer(question_id="usage", option_ids=["office"]), OptionAnswer(question_id="portability", option_ids=["often"]), OptionAnswer(question_id="budget", option_ids=["8000_12000"])], "经常出差，要轻", 0),
]

FIVE = [
    ("手机-日常", "phone", [OptionAnswer(question_id="usage", option_ids=["daily"]), OptionAnswer(question_id="budget", option_ids=["2000_4000"])], "日常聊天刷视频", 0),
    ("手机-拍照", "phone", [OptionAnswer(question_id="usage", option_ids=["camera"]), OptionAnswer(question_id="budget", option_ids=["4000_6000"])], "主要拍照", 0),
    ("平板-看视频", "tablet", [OptionAnswer(question_id="usage", option_ids=["entertainment"]), OptionAnswer(question_id="budget", option_ids=["2000_4000"])], "看视频", 0),
    ("平板-记笔记", "tablet", [OptionAnswer(question_id="usage", option_ids=["notes"]), OptionAnswer(question_id="budget", option_ids=["4000_7000"])], "手写记笔记", 0),
    ("显示器-办公", "monitor", [OptionAnswer(question_id="usage", option_ids=["office"]), OptionAnswer(question_id="connected_devices", option_ids=["windows_pc"]), OptionAnswer(question_id="budget", option_ids=["1000_2000"])], "办公", 0),
    ("显示器-设计", "monitor", [OptionAnswer(question_id="usage", option_ids=["design"]), OptionAnswer(question_id="connected_devices", option_ids=["mac"]), OptionAnswer(question_id="budget", option_ids=["2000_4000"])], "修图", 0),
    ("耳机-通勤", "headphones", [OptionAnswer(question_id="scenarios", option_ids=["commute"]), OptionAnswer(question_id="budget", option_ids=["300_1000"])], "通勤降噪", 0),
    ("耳机-通话", "headphones", [OptionAnswer(question_id="scenarios", option_ids=["calls"]), OptionAnswer(question_id="budget", option_ids=["300_1000"])], "开会通话", 0),
]


def brief(result, summary):
    def item(product):
        if product is None:
            return None
        price = product.price
        return {
            "name": product.name,
            "price_status": price.status,
            "amount_minor": price.amount_minor,
            "facts": [{"field": fact.field, "value": fact.value, "excerpt": fact.excerpt} for fact in product.facts if fact.status == "supported"][:4],
        }
    return {
        "status": result.status,
        "summary": summary.strip(),
        "primary": item(result.primary),
        "alternatives": [item(product) for product in result.alternatives],
        "sources": [source.model_dump(mode="json") for source in result.evidence_sources[:6]],
    }


async def run_case(title, category_id, answers, text, follow_up_round, config):
    load_project_env()
    secrets = load_secrets()
    model = DeepSeekGateway(secrets.model_api_key.get_secret_value(), timeout_s=config.call_timeout_s)
    raw = PageReader(max_page_bytes=config.max_page_bytes, timeout_s=config.call_timeout_s)
    reader = ThrottledReader(raw, Throttle(config.source_min_interval_s))
    catalog = PconlineCatalog(reader)
    request = RecommendRequest(request_id=title, category_id=category_id, option_answers=answers, free_text=text, follow_up_round=follow_up_round)
    buffer = StringIO()
    with redirect_stdout(buffer):
        result = await recommend(request, model=model, catalog=catalog, reader=reader, config=config)
    return {"title": title, "free_text": text, **brief(result, buffer.getvalue())}


async def main(mode: str) -> int:
    config = load_runtime_config()
    cases = LAPTOP if mode == "laptop" else LAPTOP + FIVE
    results = []
    for case in cases:
        print("RUN", case[0], file=sys.stderr)
        try:
            results.append(await run_case(*case, config))
        except Exception as exc:
            results.append({"title": case[0], "status": "exception", "error": type(exc).__name__})
    if mode == "errors":
        results.extend(await errors(config))
    json.dump(results, sys.stdout, ensure_ascii=False, indent=2)
    return 0


class BrokenCatalog:
    async def search(self, keyword):
        raise CatalogSearchError("auth")


async def errors(config):
    load_project_env()
    secrets = load_secrets()
    model = DeepSeekGateway(secrets.model_api_key.get_secret_value(), timeout_s=config.call_timeout_s)
    raw = PageReader(max_page_bytes=config.max_page_bytes, timeout_s=1)
    out = []
    request = RecommendRequest(request_id="err", category_id="laptop", option_answers=[OptionAnswer(question_id="usage", option_ids=["office"]), OptionAnswer(question_id="budget", option_ids=["5000_8000"])], free_text="写文档")
    short = config.model_copy(update={"request_timeout_s": 0.05, "source_min_interval_s": 0})
    limited = config.model_copy(update={"max_search_calls": 1, "source_min_interval_s": 0})
    for title, catalog, reader, used in [
        ("时限很短", PconlineCatalog(raw), raw, short),
        ("搜索上限为1", PconlineCatalog(ThrottledReader(raw, Throttle(0))), raw, limited),
        ("搜索失败", BrokenCatalog(), raw, config.model_copy(update={"source_min_interval_s": 0})),
    ]:
        buffer = StringIO()
        with redirect_stdout(buffer):
            result = await recommend(request, model=model, catalog=catalog, reader=reader, config=used)
        out.append({"title": title, "status": result.status, "summary": buffer.getvalue().strip()})
    return out


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "laptop")))
