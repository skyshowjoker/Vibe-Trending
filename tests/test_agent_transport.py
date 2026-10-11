import json

import pytest
import websockets

from vibe_trending.agents import JiuwenSwarmAgent


@pytest.mark.asyncio
async def test_jiuwen_e2a_transport(monkeypatch):
    async def handler(ws):
        await ws.send(json.dumps({"type": "event", "event": "connection.ack"}))
        request = json.loads(await ws.recv())
        assert request["is_stream"] is False
        assert "不要生成观测数值" in request["params"]["query"]
        plan = {"title": "GDP", "series": [{"name": "中国 GDP", "indicator": "NY.GDP.MKTP.CD"}]}
        await ws.send(json.dumps({"request_id": request["request_id"], "status": "succeeded", "response_kind": "e2a.complete", "body": {"result": {"content": json.dumps(plan)}}}))
    async with websockets.serve(handler, "127.0.0.1", 0) as server:
        port = server.sockets[0].getsockname()[1]
        monkeypatch.setenv("JIUWENSWARM_AGENT_URL", f"ws://127.0.0.1:{port}")
        plan = await JiuwenSwarmAgent().plan("中国 GDP")
        assert plan.series[0].indicator == "NY.GDP.MKTP.CD"
