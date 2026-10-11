import asyncio
from typing import List

import pytest
from pydantic import BaseModel

from app.adapters.model.base import ModelGatewayError
from app.adapters.model.fake import FakeModelGateway


class Echo(BaseModel):
    words: List[str]


def call(gateway):
    return asyncio.run(gateway.generate_json(task="echo", payload={"text": "hi"}, output_schema=Echo))


def test_valid_json_is_parsed_into_the_schema():
    gateway = FakeModelGateway(['{"words": ["a", "b"]}'])
    assert call(gateway).words == ["a", "b"]


def test_non_json_output_becomes_invalid_output_error():
    gateway = FakeModelGateway(["好的，以下是结果：words=a,b"])
    with pytest.raises(ModelGatewayError) as e:
        call(gateway)
    assert e.value.kind == "invalid_output"


def test_json_with_wrong_shape_becomes_invalid_output_error():
    gateway = FakeModelGateway(['{"words": "a"}'])
    with pytest.raises(ModelGatewayError) as e:
        call(gateway)
    assert e.value.kind == "invalid_output"


@pytest.mark.parametrize("kind", ["timeout", "auth", "quota"])
def test_scripted_service_errors_keep_their_kind(kind):
    gateway = FakeModelGateway([ModelGatewayError(kind)])
    with pytest.raises(ModelGatewayError) as e:
        call(gateway)
    assert e.value.kind == kind


def test_calls_are_recorded_with_task_payload_and_schema():
    gateway = FakeModelGateway(['{"words": []}'])
    call(gateway)
    assert gateway.calls[0]["task"] == "echo"
    assert gateway.calls[0]["payload"] == {"text": "hi"}
    assert "words" in gateway.calls[0]["output_schema"]["properties"]
