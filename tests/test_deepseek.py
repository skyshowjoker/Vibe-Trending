import json

import httpx
import pytest

from vibe_trending.agents import DeepSeekAgent


@pytest.mark.asyncio
async def test_existing_deepseek_config(tmp_path, monkeypatch):
    path = tmp_path / "config.yaml"
    path.write_text("models:\n  defaults:\n    - model_client_config:\n        model_name: deepseek-test\n        api_base: https://api.deepseek.com\n        api_key: ${API_KEY}\n")
    (tmp_path / ".env").write_text("API_KEY=test-only\n")
    monkeypatch.delenv("API_KEY", raising=False)
    monkeypatch.setenv("VIBE_MODEL_CONFIG", str(path))
    agent = DeepSeekAgent()
    original_client = httpx.AsyncClient

    def handler(request):
        assert request.headers["Authorization"] == "Bearer test-only"
        body = json.loads(request.content)
        assert body["model"] == "deepseek-test"
        assert body["stream"] is False
        plan = {"title": "中国 GDP", "series": [{"name": "中国 GDP", "indicator": "NY.GDP.MKTP.CD"}]}
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(plan)}}]})

    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: original_client(
        transport=httpx.MockTransport(handler), **kwargs))
    assert (await agent.plan("中国 GDP")).title == "中国 GDP"
