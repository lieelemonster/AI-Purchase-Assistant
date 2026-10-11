import httpx
import openai
import pytest

from app.adapters.model.deepseek import classify_model_error


def http_error(status, error_type):
    request = httpx.Request("POST", "https://api.deepseek.com/chat/completions")
    response = httpx.Response(status, request=request)
    return error_type("failed", response=response, body=None)


@pytest.mark.parametrize(
    "exc, kind",
    [
        (http_error(401, openai.AuthenticationError), "auth"),
        (http_error(429, openai.RateLimitError), "quota"),
        (openai.APITimeoutError(request=httpx.Request("POST", "https://api.deepseek.com/chat/completions")), "timeout"),
        (TimeoutError(), "timeout"),
    ],
)
def test_sdk_errors_are_classified(exc, kind):
    assert classify_model_error(exc).kind == kind
