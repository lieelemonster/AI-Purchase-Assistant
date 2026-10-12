from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_lists_the_first_version_categories():
    response = client.get("/v1/categories")
    assert response.status_code == 200
    assert response.json() == {
        "categories": [
            {"id": "laptop", "name": "笔记本电脑"},
            {"id": "phone", "name": "手机"},
            {"id": "tablet", "name": "平板电脑"},
            {"id": "headphones", "name": "耳机"},
        ]
    }
