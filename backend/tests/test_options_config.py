import pytest
from pydantic import ValidationError

from app.config.categories import category_ids
from app.config.option_loader import UnknownCategoryError, load_options
from app.schemas.options import OptionConfig, Question


@pytest.mark.parametrize("category_id", sorted(category_ids()))
def test_every_category_has_a_valid_versioned_option_file(category_id):
    config = load_options(category_id)
    assert config.category_id == category_id
    assert config.version
    for question in config.questions:
        if question.kind == "choice":
            assert len(question.options) >= 2
        else:
            assert question.options == []


def test_unknown_category_has_no_options():
    with pytest.raises(UnknownCategoryError):
        load_options("car")


def test_duplicate_question_ids_are_rejected():
    question = {"id": "usage", "label": "用途", "multiple": True,
                "options": [{"id": "a", "label": "A"}, {"id": "b", "label": "B"}]}
    with pytest.raises(ValidationError, match="重复的问题 ID"):
        OptionConfig(category_id="laptop", version="v1", questions=[question, question])


def test_duplicate_option_ids_are_rejected():
    with pytest.raises(ValidationError, match="重复的选项 ID"):
        Question(id="usage", label="用途", multiple=True,
                 options=[{"id": "a", "label": "A"}, {"id": "a", "label": "B"}])


def test_question_needs_at_least_two_options():
    with pytest.raises(ValidationError):
        Question(id="usage", label="用途", multiple=True, options=[{"id": "a", "label": "A"}])
