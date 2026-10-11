import asyncio

from fastapi.testclient import TestClient

from vibe_trending import app as module
from vibe_trending.agents import RuleAgent
from vibe_trending.models import Plan
from vibe_trending.store import Store


def test_rule_plan():
    plan = asyncio.run(RuleAgent().plan("对比中国和美国 2015 到 2024 年人均 GDP"))
    assert len(plan.series) == 2
    assert plan.start_year == 2015
    assert all(s.indicator == "NY.GDP.PCAP.CD" for s in plan.series)


def test_collect_edit_update_restore_export(tmp_path, monkeypatch):
    from vibe_trending.collectors import DirectCollector
    monkeypatch.setattr(module, 'collector', DirectCollector(module.sources))
    monkeypatch.setattr(module, "store", Store(tmp_path / "db.sqlite"))
    class Source:
        async def collect(self, series, plan):
            return {"points": [{"date": "2020", "value": 10, "source_url": "https://example.com/source", "quality": "source_verified", "manual": False, "collected_at": "2026"}], "raw": {"original": 10}, "source_url": "https://example.com/source", "collected_at": "2026"}
    monkeypatch.setitem(module.sources, "worldbank", Source())
    with TestClient(module.app) as client:
        plan = Plan(title="测试", series=[{"name": "GDP", "indicator": "NY.GDP.MKTP.CD"}])
        p = client.post("/api/projects", json={"plan": plan.model_dump()}).json()
        base = "/api/projects/" + p["id"]
        p = client.post(base + "/collect").json()
        assert p["tasks"][0]["status"] == "completed"
        sid = p["series"][0]["id"]
        client.patch(base + "/points", json={"series_id": sid, "date": "2020", "value": 99, "reason": "校正", "source_url": "https://example.com/source"})
        updated = client.post(base + "/collect").json()
        assert updated["series"][0]["points"][0]["value"] == 99
        assert updated["series"][0]["points"][0]["manual"]
        versions = client.get(base + "/versions").json()
        assert len(versions) >= 5
        assert "source_url" in client.get(base + "/export.csv").text
        assert client.put(base + "/schedule", json={"enabled": True, "timezone": "Bad/Zone"}).status_code == 422
