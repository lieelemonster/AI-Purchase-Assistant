from fastapi.testclient import TestClient

from app.adapters.model.fake import FakeModelGateway
from app.api import recommendations as recommendations_api
from app.main import app
from tests.test_recommend_flow import config, make_db, normalize_reply, selection_reply

client = TestClient(app)


def use_fakes(tmp_path):
    db_path = tmp_path / "products.db"
    make_db(db_path)
    app.dependency_overrides[recommendations_api.get_model] = lambda: FakeModelGateway([
        normalize_reply(), selection_reply(),
    ])
    app.dependency_overrides[recommendations_api.get_catalog] = lambda: None
    app.dependency_overrides[recommendations_api.get_reader] = lambda: None
    app.dependency_overrides[recommendations_api.get_config] = lambda: config(
        db_path, source_min_interval_s=0, request_timeout_s=30,
    )


def test_response_echoes_request_id_and_input_version(tmp_path):
    use_fakes(tmp_path)
    response = client.post("/v1/recommendations", json={
        "request_id": "req-42",
        "input_version": "options-v1",
        "category_id": "laptop",
        "option_answers": [
            {"question_id": "usage", "option_ids": ["office"]},
            {"question_id": "budget", "option_ids": ["5000_8000"]},
        ],
        "free_text": "主要写文档",
    })
    app.dependency_overrides.clear()
    assert response.status_code == 200
    body = response.json()
    assert body["request_id"] == "req-42"
    assert body["input_version"] == "options-v1"
    assert body["status"] == "success"


def test_client_cannot_submit_price(tmp_path):
    use_fakes(tmp_path)
    response = client.post("/v1/recommendations", json={
        "request_id": "req-42",
        "input_version": "options-v1",
        "category_id": "laptop",
        "price": 1,
    })
    app.dependency_overrides.clear()
    assert response.status_code == 422


def test_client_cannot_submit_verified(tmp_path):
    use_fakes(tmp_path)
    response = client.post("/v1/recommendations", json={
        "request_id": "req-42",
        "input_version": "options-v1",
        "category_id": "laptop",
        "verified": True,
    })
    app.dependency_overrides.clear()
    assert response.status_code == 422
