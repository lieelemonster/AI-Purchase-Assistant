import json

import pytest
from fastapi.testclient import TestClient

from app.config.settings import RUNTIME_FILE, ConfigError, load_runtime_config, load_secrets
from app.main import app

PARAMS = [
    "max_candidates",
    "max_search_calls",
    "max_pages",
    "max_page_bytes",
    "call_timeout_s",
    "request_timeout_s",
    "max_retries",
    "concurrency",
    "source_min_interval_s",
    "model_max_output_tokens",
    "rate_limit_per_minute",
    "max_concurrent_requests",
]


def write_runtime(tmp_path, data):
    path = tmp_path / "runtime.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def default_data():
    return json.loads(RUNTIME_FILE.read_text(encoding="utf-8"))


def test_default_runtime_file_has_all_params():
    assert sorted(default_data()) == sorted(PARAMS)
    load_runtime_config()


@pytest.mark.parametrize("param", PARAMS)
def test_missing_param_error_names_the_param(tmp_path, param):
    data = default_data()
    del data[param]
    with pytest.raises(ConfigError, match=param):
        load_runtime_config(write_runtime(tmp_path, data))


def test_negative_request_timeout_is_rejected(tmp_path):
    data = default_data()
    data["request_timeout_s"] = -5
    with pytest.raises(ConfigError, match="request_timeout_s"):
        load_runtime_config(write_runtime(tmp_path, data))


def test_misspelled_param_is_rejected(tmp_path):
    data = default_data()
    data["max_candidate"] = data.pop("max_candidates")
    with pytest.raises(ConfigError, match="max_candidate"):
        load_runtime_config(write_runtime(tmp_path, data))


def test_secrets_come_from_env_and_are_masked():
    secrets = load_secrets({"MODEL_API_KEY": "sk-test-123", "SEARCH_API_KEY": ""})
    assert secrets.model_api_key.get_secret_value() == "sk-test-123"
    assert secrets.search_api_key is None
    assert "sk-test-123" not in repr(secrets)


def test_health_does_not_expose_keys(monkeypatch):
    monkeypatch.setenv("MODEL_API_KEY", "sk-test-123")
    response = TestClient(app).get("/health")
    assert "sk-test-123" not in response.text
