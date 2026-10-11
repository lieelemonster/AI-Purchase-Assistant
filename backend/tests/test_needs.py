import asyncio
import json

import pytest

from app.adapters.model.fake import FakeModelGateway
from app.core.needs.normalize import InvalidNeedInput, normalize_needs
from app.schemas.need import OptionAnswer

FREE_TEXT = "我想买笔记本，主要写文档，预算还没想好"
ANSWERS = [OptionAnswer(question_id="portability", option_ids=["often"])]


def text_req(quote, topic="usage", statement="主要用来写文档"):
    return {"topic": topic, "statement": statement, "source": {"kind": "free_text", "quote": quote}}


def option_req(question_id, option_id, topic="portability", statement="经常带出门"):
    return {"topic": topic, "statement": statement,
            "source": {"kind": "option", "question_id": question_id, "option_id": option_id}}


def normalize(extraction, answers=ANSWERS, free_text=FREE_TEXT):
    gateway = FakeModelGateway([json.dumps(extraction, ensure_ascii=False)])
    profile = asyncio.run(normalize_needs("laptop", answers, free_text, gateway))
    return profile, gateway


def test_valid_requirements_get_program_assigned_ids_and_market():
    profile, _ = normalize({
        "requirements": [text_req("主要写文档"), option_req("portability", "often")],
        "unknowns": ["budget"],
    })
    assert [r.requirement_id for r in profile.requirements] == ["r1", "r2"]
    assert profile.requirements[0].source.quote == "主要写文档"
    assert profile.unknowns == ["budget"]
    assert profile.market_context.region == "CN"
    assert profile.market_context.currency == "CNY"


def test_quote_not_in_user_text_is_rejected():
    profile, _ = normalize({"requirements": [
        text_req("预算 5000", topic="budget", statement="预算 5000 元"),
        text_req("主要写文档"),
    ]})
    assert [r.topic for r in profile.requirements] == ["usage"]


def test_option_not_in_config_is_rejected():
    profile, _ = normalize({"requirements": [option_req("portability", "teleport")]})
    assert profile.requirements == []


def test_option_the_user_did_not_select_is_rejected():
    profile, _ = normalize({"requirements": [option_req("portability", "desk", statement="放桌上")]})
    assert profile.requirements == []


def test_conflict_referencing_a_rejected_requirement_is_dropped():
    profile, _ = normalize({
        "requirements": [text_req("主要写文档"), text_req("不存在的话"), option_req("portability", "often")],
        "conflicts": [
            {"description": "有效冲突", "requirement_indexes": [0, 2]},
            {"description": "引用了被拒绝的需求", "requirement_indexes": [0, 1]},
        ],
    })
    assert [(c.description, c.requirement_ids) for c in profile.conflicts] == [("有效冲突", ["r1", "r2"])]


def test_model_receives_questions_answers_and_text():
    _, gateway = normalize({"requirements": []})
    payload = gateway.calls[0]["payload"]
    assert payload["category"] == {"id": "laptop", "name": "笔记本电脑"}
    assert "budget" in [q["id"] for q in payload["questions"]]
    assert payload["option_answers"] == [{"question_id": "portability", "option_ids": ["often"]}]
    assert payload["free_text"] == FREE_TEXT


@pytest.mark.parametrize("answers, message", [
    ([OptionAnswer(question_id="color", option_ids=["red"])], "未知问题"),
    ([OptionAnswer(question_id="budget", option_ids=["over_9000"])], "没有选项"),
    ([OptionAnswer(question_id="budget", option_ids=["under_5000", "over_12000"])], "单选题"),
    ([OptionAnswer(question_id="os", option_ids=["macos"]), OptionAnswer(question_id="os", option_ids=["windows"])], "重复作答"),
])
def test_invalid_client_answers_are_rejected_before_calling_the_model(answers, message):
    gateway = FakeModelGateway([])
    with pytest.raises(InvalidNeedInput, match=message):
        asyncio.run(normalize_needs("laptop", answers, "", gateway))
    assert gateway.calls == []
