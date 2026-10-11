import json

from fastapi.testclient import TestClient

from app.config.option_loader import OPTIONS_DIR
from app.main import app

client = TestClient(app)


def test_laptop_options_match_the_config_file():
    response = client.get("/v1/options", params={"category_id": "laptop"})
    assert response.status_code == 200
    expected = json.loads((OPTIONS_DIR / "laptop.json").read_text(encoding="utf-8"))
    assert response.json() == expected
    assert response.json()["version"] == "v1"


def test_unknown_category_returns_404_with_error_code():
    response = client.get("/v1/options", params={"category_id": "car"})
    assert response.status_code == 404
    assert response.json()["error"] == "unknown_category"


def test_missing_category_id_is_rejected():
    assert client.get("/v1/options").status_code == 422
