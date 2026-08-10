from __future__ import annotations

from tests.conftest import APITestContext


def test_chatbot_frontend_is_served_by_fastapi(api_context: APITestContext):
    response = api_context.client.get("/")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "FinTrack AI — Financial Chatbot" in response.text
    assert 'id="chatScroll"' in response.text
    assert 'id="messages"' in response.text
    assert 'id="activeStep"' in response.text
    assert 'id="anytimeMessages"' in response.text
    assert 'id="queryForm"' in response.text
    assert "Money planning, made conversational" in response.text
    assert "Ask anything, anytime" in response.text
    assert "streamlit" not in response.text.lower()


def test_frontend_assets_contain_guided_and_free_query_flows(api_context: APITestContext):
    css = api_context.client.get("/static/app.css")
    javascript = api_context.client.get("/static/app.js")
    assert css.status_code == 200
    assert javascript.status_code == 200
    assert ".chatbot" in css.text
    assert ".product-story" in css.text
    assert "--orange: #f97316" in css.text
    assert "@media (max-width: 680px)" in css.text
    assert "/api/auth/login" in javascript.text
    assert "/api/income/latest" in javascript.text
    assert "/api/expenses/latest" in javascript.text
    assert "/api/goals/recommendation" in javascript.text
    assert "/api/analytics/summary" in javascript.text
    assert "General AI responses are coming soon" in javascript.text
    assert "addAnytimeMessage" in javascript.text
    assert "renderAnytimeMessages" in javascript.text
    assert "openai" not in javascript.text.lower()


def test_removed_unsafe_routes_remain_absent(api_context: APITestContext):
    assert api_context.client.get("/users").status_code == 404
    paths = api_context.client.get("/openapi.json").json()["paths"]
    assert "/users" not in paths
    assert "/" not in paths
