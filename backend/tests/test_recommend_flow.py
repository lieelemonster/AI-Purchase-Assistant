import asyncio
import json
import sqlite3
import time

from app.adapters.model.base import ModelGatewayError
from app.adapters.model.fake import FakeModelGateway
from app.catalog.library import SPEC_COLUMNS
from app.config.settings import load_runtime_config
from app.core.recommendation.recommend import RecommendRequest, recommend
from app.schemas.need import OptionAnswer


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


def make_db(path):
    columns = ["id", "brand", "model", "reference_price", "source_url", *SPEC_COLUMNS["laptops"]]
    db = sqlite3.connect(path)
    db.execute(f"CREATE TABLE laptops ({', '.join(name + ' TEXT' for name in columns)})")
    rows = [
        ("1", "示例", "示例本A", "5999", "https://example.test/a", "16GB"),
        ("2", "示例", "示例本B", "6999", "https://example.test/b", "16GB"),
        ("3", "示例", "示例本C", "7999", "https://example.test/c", "32GB"),
        ("4", "示例", "超预算", "9000", "https://example.test/d", "16GB"),
        ("5", "示例", "价格未确认", "未确认", "", "16GB"),
    ]
    memory_index = columns.index("memory")
    for row in rows:
        values = [""] * len(columns)
        values[0], values[1], values[2], values[3], values[4] = row[:5]
        values[memory_index] = row[5]
        db.execute(f"INSERT INTO laptops VALUES ({', '.join('?' for _ in columns)})", values)
    db.commit()
    db.close()


def config(path, **updates):
    return load_runtime_config().model_copy(update={"catalog_db_path": str(path), **updates})


def normalize_reply():
    return json.dumps({"requirements": [{
        "topic": "usage", "statement": "写文档",
        "source": {"kind": "option", "question_id": "usage", "option_id": "office"},
    }]}, ensure_ascii=False)


def selection_reply():
    return json.dumps({
        "primary": {"product_id": "laptops:1", "reason": "适合写文档"},
        "alternatives": [
            {"product_id": "laptops:2", "reason": "适合写文档"},
            {"product_id": "laptops:5", "reason": "适合写文档，参考价未确认"},
        ],
        "notes": "备选里有一款价格未确认",
    }, ensure_ascii=False)


def test_catalog_selection_fills_name_and_price_from_the_library(tmp_path):
    db_path = tmp_path / "products.db"
    make_db(db_path)
    result = asyncio.run(recommend(
        request(),
        model=FakeModelGateway([normalize_reply(), selection_reply()]),
        catalog=None,
        reader=None,
        config=config(db_path),
    ))
    assert result.status == "success"
    assert result.primary.name == "示例 示例本A"
    assert result.primary.price.amount_minor == 599900
    assert [item.name for item in result.alternatives] == ["示例 示例本B", "示例 示例本C"]
    assert "内存至少 16GB" in result.primary.reasons[0].text
    assert all("超预算" not in item.name for item in [result.primary, *result.alternatives])
    memory = next(fact.value for fact in result.primary.facts if fact.field == "memory")
    assert memory == "16GB"


def test_newest_release_among_the_three_is_primary(tmp_path):
    db_path = tmp_path / "products.db"
    make_db(db_path)
    db = sqlite3.connect(db_path)
    db.execute("UPDATE laptops SET release_date = '2024-01' WHERE id = '1'")
    db.execute("UPDATE laptops SET release_date = '2026-03' WHERE id = '2'")
    db.execute("UPDATE laptops SET release_date = '2025-05' WHERE id = '5'")
    db.commit()
    db.close()
    result = asyncio.run(recommend(
        request(),
        model=FakeModelGateway([normalize_reply(), selection_reply()]),
        catalog=None,
        reader=None,
        config=config(db_path),
    ))
    assert result.primary.name == "示例 示例本B"
    assert [item.name for item in result.alternatives] == ["示例 价格未确认", "示例 示例本A"]


def test_invalid_product_id_falls_back_to_price_order(tmp_path):
    db_path = tmp_path / "products.db"
    make_db(db_path)
    invented = json.dumps({
        "primary": {"product_id": "laptops:999", "reason": "适合写文档"},
        "alternatives": [],
    }, ensure_ascii=False)
    result = asyncio.run(recommend(
        request(),
        model=FakeModelGateway([normalize_reply(), invented, invented]),
        catalog=None,
        reader=None,
        config=config(db_path, max_retries=1),
    ))
    assert result.primary.name == "示例 示例本A"
    assert [item.name for item in result.alternatives] == ["示例 示例本B", "示例 示例本C"]
    assert "999" not in result.primary.name


def test_clarification_is_replaced_by_a_catalog_recommendation(tmp_path):
    db_path = tmp_path / "products.db"
    make_db(db_path)
    asked = json.dumps({
        "need_clarification": True,
        "questions": ["更看重续航还是重量？"],
        "primary": {"product_id": "laptops:1", "reason": "适合写文档"},
    }, ensure_ascii=False)
    result = asyncio.run(recommend(
        request(),
        model=FakeModelGateway([normalize_reply(), asked, asked]),
        catalog=None,
        reader=None,
        config=config(db_path),
    ))
    assert result.follow_up is None
    assert result.primary is not None
    assert result.primary.name == "示例 示例本A"
    assert "模型" not in result.primary.reasons[0].text


def test_request_timeout_finishes_within_the_limit(tmp_path):
    db_path = tmp_path / "products.db"
    make_db(db_path)

    class Slow(FakeModelGateway):
        async def _complete(self, *, task, payload, output_schema):
            await asyncio.sleep(30)
            return await super()._complete(task=task, payload=payload, output_schema=output_schema)

    started = time.monotonic()
    result = asyncio.run(recommend(
        request(),
        model=Slow([normalize_reply()]),
        catalog=None,
        reader=None,
        config=config(db_path, request_timeout_s=1),
    ))
    assert result.status == "timeout"
    assert time.monotonic() - started < 3


def test_quota_error_is_not_reported_as_success(tmp_path):
    db_path = tmp_path / "products.db"
    make_db(db_path)
    result = asyncio.run(recommend(
        request(),
        model=FakeModelGateway([ModelGatewayError("quota")]),
        catalog=None,
        reader=None,
        config=config(db_path),
    ))
    assert result.status == "service_unavailable"
