import asyncio
import json

import pytest
from pydantic import ValidationError

from app.adapters.model.fake import FakeModelGateway
from app.config.categories import category_ids
from app.config.option_loader import load_options
from app.core.needs.follow_up import find_missing, load_required_info, plan_follow_up
from app.schemas.need import Conflict, NeedProfile, OptionAnswer, Requirement
from app.schemas.result import RecommendationResult


def profile(category_id="laptop", answers=(), requirements=(), unknowns=(), conflicts=()):
    return NeedProfile(category_id=category_id, option_answers=list(answers), requirements=list(requirements),
                       unknowns=list(unknowns), conflicts=list(conflicts))


def answer(question_id, *option_ids):
    return OptionAnswer(question_id=question_id, option_ids=list(option_ids))


def text_requirement(topic, quote, requirement_id="r1"):
    return Requirement(requirement_id=requirement_id, topic=topic, statement=quote,
                       source={"kind": "free_text", "quote": quote})


def drafted(*questions):
    return FakeModelGateway([json.dumps({"questions": list(questions)}, ensure_ascii=False)])


def plan(need, gateway, follow_up_round=0):
    return asyncio.run(plan_follow_up(need, follow_up_round, gateway))


def test_only_category_selected_asks_one_round_about_usage_and_budget():
    gateway = drafted({"question_id": "usage", "text": "你打算主要用它做什么呢？"},
                      {"question_id": "budget", "text": "大概准备花多少钱？"})
    follow_up = plan(profile(), gateway)
    assert follow_up.round == 1
    assert follow_up.missing_question_ids == ["usage", "budget"]
    assert [q.question_id for q in follow_up.questions] == ["usage", "budget"]
    assert gateway.calls[0]["payload"]["missing"][0] == {"question_id": "usage", "question": "你主要用它来做什么？"}


def test_complete_answers_need_no_follow_up_and_no_model_call():
    gateway = FakeModelGateway([])
    assert plan(profile(answers=[answer("usage", "office"), answer("budget", "5000_8000")]), gateway) is None
    assert gateway.calls == []


def test_not_sure_counts_as_unknown():
    need = profile(answers=[answer("usage", "office"), answer("budget", "not_sure")])
    assert find_missing(need) == ["budget"]


def test_requirement_from_free_text_counts_as_known():
    need = profile(answers=[answer("budget", "under_5000")], requirements=[text_requirement("usage", "主要写文档")])
    assert find_missing(need) == []


def test_topic_listed_as_unknown_is_missing_even_with_a_requirement():
    need = profile(answers=[answer("usage", "office")], requirements=[text_requirement("budget", "预算还没想好")],
                   unknowns=["budget"])
    assert find_missing(need) == ["budget"]


def test_monitor_also_requires_connected_devices():
    need = profile("monitor", answers=[answer("usage", "office"), answer("budget", "1000_2000")])
    assert find_missing(need) == ["connected_devices"]


def test_after_one_round_still_missing_info_proceeds_as_unknown():
    gateway = FakeModelGateway([])
    assert plan(profile(), gateway, follow_up_round=1) is None
    assert gateway.calls == []


def test_conflict_alone_triggers_a_clarifying_question():
    conflict = Conflict(description="选了 5000 元以下，又写了预算不限", requirement_ids=["r1", "r2"])
    need = profile(answers=[answer("usage", "office"), answer("budget", "under_5000")], conflicts=[conflict])
    follow_up = plan(need, drafted({"question_id": None, "text": "你的预算到底是 5000 元以内还是不限呢？"}))
    assert follow_up.missing_question_ids == []
    assert follow_up.conflicts == [conflict]
    assert follow_up.questions[0].question_id is None


def test_model_questions_for_unrelated_items_are_dropped_and_gaps_filled():
    follow_up = plan(profile(answers=[answer("usage", "office")]), drafted({"question_id": "os", "text": "喜欢什么系统？"}))
    assert [(q.question_id, q.text) for q in follow_up.questions] == [("budget", "预算大概多少？")]


@pytest.mark.parametrize("category_id", sorted(category_ids()))
def test_required_questions_exist_in_option_config(category_id):
    question_ids = {q.id for q in load_options(category_id).questions}
    assert set(load_required_info().required_questions[category_id]) <= question_ids


def test_need_more_info_result_requires_follow_up():
    with pytest.raises(ValidationError):
        RecommendationResult(request_id="r", status="need_more_info", checked_at="2026-10-11T12:00:00Z")
    follow_up = plan(profile(), drafted())
    RecommendationResult(request_id="r", status="need_more_info", follow_up=follow_up, checked_at="2026-10-11T12:00:00Z")
