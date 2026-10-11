import asyncio
from datetime import datetime, timezone

import httpx
import pytest
from httpx import ASGITransport

from app.api.limiter import RequestLimiter
from app.api.recommendations import get_catalog, get_model, get_reader
from app.main import app
from app.schemas.result import RecommendationResult


def empty_result():
    return RecommendationResult(request_id="req", status="timeout", checked_at=datetime.now(timezone.utc))


@pytest.fixture
def client_app():
    app.dependency_overrides[get_model] = lambda: None
    app.dependency_overrides[get_catalog] = lambda: None
    app.dependency_overrides[get_reader] = lambda: None
    app.state.limiter = RequestLimiter(per_minute=5, max_concurrent=2)
    app.state.recommend_override = None
    yield app
    app.dependency_overrides.clear()
    app.state.recommend_override = None
    app.state.limiter = RequestLimiter(per_minute=30, max_concurrent=2)


def test_sixth_request_is_rejected():
    limiter = RequestLimiter(per_minute=5, max_concurrent=10)
    now = 1000.0
    assert [limiter.enter(now) for _ in range(5)] == ["ok"] * 5
    assert limiter.enter(now) == "rate_limited"


def test_third_overlapping_request_is_busy():
    limiter = RequestLimiter(per_minute=30, max_concurrent=2)
    assert limiter.enter(1) == "ok"
    assert limiter.enter(1) == "ok"
    assert limiter.enter(1) == "busy"
    limiter.leave()
    assert limiter.enter(1) == "ok"


def test_api_returns_429_after_five_requests(client_app):
    async def instant():
        return empty_result()

    client_app.state.recommend_override = instant

    async def run():
        transport = ASGITransport(app=client_app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            codes = []
            bodies = []
            for index in range(10):
                response = await client.post("/v1/recommendations", json={
                    "request_id": f"req-{index}",
                    "input_version": "v1",
                    "category_id": "laptop",
                })
                codes.append(response.status_code)
                bodies.append(response.text)
            return codes, bodies

    codes, bodies = asyncio.run(run())
    assert codes[:5] == [200] * 5
    assert codes[5:] == [429] * 5
    assert "请求过于频繁" in bodies[5]


def test_third_concurrent_request_is_busy_and_the_server_stays_up(client_app):
    client_app.state.limiter = RequestLimiter(per_minute=30, max_concurrent=2)

    async def slow():
        await asyncio.sleep(0.3)
        return empty_result()

    client_app.state.recommend_override = slow

    async def run():
        transport = ASGITransport(app=client_app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            calls = [
                client.post("/v1/recommendations", json={
                    "request_id": f"req-{index}",
                    "input_version": "v1",
                    "category_id": "laptop",
                })
                for index in range(3)
            ]
            responses = await asyncio.gather(*calls)
            return [item.status_code for item in responses], [item.text for item in responses]

    codes, bodies = asyncio.run(run())
    assert sorted(codes) == [200, 200, 503]
    assert any("服务繁忙" in text for text in bodies)
