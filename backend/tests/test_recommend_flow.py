import asyncio
import json
import time
from datetime import datetime, timezone

from app.adapters.catalog.pconline import CatalogHit
from app.adapters.model.base import ModelGateway, ModelGatewayError
from app.adapters.model.fake import FakeModelGateway
from app.config.settings import load_runtime_config
from app.core.recommendation.recommend import RecommendRequest, recommend
from app.schemas.evidence import EvidenceDocument
from app.schemas.need import OptionAnswer

NOW = datetime(2026, 10, 11, tzinfo=timezone.utc)
SPEC = "上市时间 | 2024年\n处理器 | 示例芯片\n内存容量 | 16GB\n"
NAMES = {"101": "示例本A", "102": "示例本B", "103": "示例本C"}
PRICES = {"101": "5999", "102": "6999", "103": "7999"}


def request():
    return RecommendRequest(
        request_id="req-1",
        category_id="laptop",
        option_answers=[
            OptionAnswer(question_id="usage", option_ids=["office"]),
            OptionAnswer(question_id="budget", option_ids=["5000_8000"]),
        ],
        free_text="主要写文档",
    )


def config(**updates):
    return load_runtime_config().model_copy(update=updates)


class Pages:
    async def read(self, url, evidence_id):
        product_id = url.rstrip("/").split("/")[-1].split("_")[0].split(".")[0]
        name = NAMES[product_id]
        if "_price" in url:
            text = f"参考价：￥{PRICES[product_id]}（行货价格）"
            title = name + "价格"
        else:
            text, title = SPEC, name + "参数"
        return EvidenceDocument(evidence_id=evidence_id, url=url, final_url=url, title=title, fetched_at=NOW,
                                fetch_status="ok", content_hash="h", text=text)


class Catalog:
    def __init__(self, delay=0):
        self.delay = delay

    async def search(self, keyword):
        if self.delay:
            await asyncio.sleep(self.delay)
        return [
            CatalogHit(product_id=pid, name=name, category_dir="notebook", brand_dir="demo", discontinued=False,
                       url=f"https://product.pconline.com.cn/notebook/demo/{pid}.html")
            for pid, name in NAMES.items()
        ]


class ScriptThenRank(ModelGateway):
    def __init__(self, replies):
        self.replies = list(replies)

    async def _complete(self, *, task, payload, output_schema):
        if self.replies:
            reply = self.replies.pop(0)
            if isinstance(reply, Exception):
                raise reply
            return reply
        ranking = [item["candidate_id"] for item in payload["candidates"][:3]]
        reasons = {}
        for item in payload["candidates"][:3]:
            fact_id = item["facts"][0]["fact_id"]
            reasons[item["candidate_id"]] = [{
                "need_refs": ["r1"],
                "fact_refs": [fact_id],
                "conclusion_type": "fact",
                "text": "{{name:%s}}适合写文档{{fact:%s}}" % (item["candidate_id"], fact_id),
            }]
        return json.dumps({"ranking": ranking, "reasons": reasons}, ensure_ascii=False)


def scripted():
    return [
        json.dumps({"requirements": [{
            "topic": "usage", "statement": "写文档",
            "source": {"kind": "option", "question_id": "usage", "option_id": "office"},
        }]}, ensure_ascii=False),
        json.dumps({"candidates": [
            {"brand_hint": "示例", "model_hint": "示例本A"},
            {"brand_hint": "示例", "model_hint": "示例本B"},
            {"brand_hint": "示例", "model_hint": "示例本C"},
        ]}, ensure_ascii=False),
        json.dumps({"keywords": [
            {"candidate_id": "c1", "keyword": "示例本A"},
            {"candidate_id": "c2", "keyword": "示例本B"},
            {"candidate_id": "c3", "keyword": "示例本C"},
        ]}, ensure_ascii=False),
        json.dumps({"choices": [
            {"candidate_id": "c1", "product_id": "101"},
            {"candidate_id": "c2", "product_id": "102"},
            {"candidate_id": "c3", "product_id": "103"},
        ]}, ensure_ascii=False),
    ]


def test_fake_services_return_one_primary_and_two_alternatives():
    result = asyncio.run(recommend(
        request(),
        model=ScriptThenRank(scripted()),
        catalog=Catalog(),
        reader=Pages(),
        config=config(source_min_interval_s=0, request_timeout_s=30),
    ))
    assert result.status == "success"
    assert result.primary.candidate_id == "c1"
    assert [item.candidate_id for item in result.alternatives] == ["c2", "c3"]
    assert result.primary.price.amount_minor == 599900


def test_search_timeout_finishes_within_the_limit():
    started = time.monotonic()
    result = asyncio.run(recommend(
        request(),
        model=FakeModelGateway(scripted()[:3]),
        catalog=Catalog(delay=30),
        reader=Pages(),
        config=config(source_min_interval_s=0, request_timeout_s=3),
    ))
    assert result.status == "timeout"
    assert time.monotonic() - started < 4


def test_quota_error_is_not_reported_as_success():
    result = asyncio.run(recommend(
        request(),
        model=FakeModelGateway([ModelGatewayError("quota")]),
        catalog=Catalog(),
        reader=Pages(),
        config=config(source_min_interval_s=0),
    ))
    assert result.status == "service_unavailable"
