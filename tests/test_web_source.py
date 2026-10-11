import pytest

from vibe_trending.models import Plan, SeriesPlan
from vibe_trending.web_source import WebSource, public_url, validate_point


def context():
    s = SeriesPlan(name="汽车销量", indicator="汽车销量", source="web", country="中国", unit="万辆", frequency="monthly")
    return s, Plan(title="销量", start_year=2024, end_year=2024, series=[s])


def test_quote_validation():
    s, plan = context()
    text = "2024年1月中国汽车销量为200万辆。"
    item = dict(date="2024-01", value=200, value_text="200", unit="万辆", quote=text)
    assert validate_point(item, text, s, plan)["quality"] == "evidence_matched"
    for bad in [dict(value=999), dict(quote="凭空编造的数据引句200万辆"), dict(date="2024-02"), dict(unit="辆"), dict(value_text="估算200")]:
        with pytest.raises(ValueError):
            validate_point({**item, **bad}, text, s, plan)
    with pytest.raises(ValueError):
        validate_point({**item, "quote": text.replace("200", "1200")}, text.replace("200", "1200"), s, plan)


@pytest.mark.asyncio
async def test_private_url_rejected():
    with pytest.raises(ValueError):
        await public_url("http://127.0.0.1:8088/")


@pytest.mark.asyncio
async def test_collection_conflicts_and_partial_failures(monkeypatch):
    s, plan = context()
    s.urls = ["https://example.com/a", "https://example.com/b", "https://example.com/c"]
    async def fetch(self, url):
        if url.endswith('/c'):
            raise ValueError("blocked")
        return dict(url=url, body="raw", sha256="hash", text="2024年1月汽车销量200万辆。2024年2月汽车销量300万辆。2024年1月汽车销量210万辆。")
    calls = 0
    async def model(self, instruction, prompt):
        nonlocal calls
        calls += 1
        value = 200 if calls == 1 else 210
        return {"points": [dict(date="2024-01", value=value, value_text=str(value), unit="万辆", quote=f"2024年1月汽车销量{value}万辆。"), dict(date="2024-02", value=300, value_text="300", unit="万辆", quote="2024年2月汽车销量300万辆。") ]}
    from vibe_trending import web_source
    class Model:
        json_call = model
    monkeypatch.setattr(web_source, "DeepSeekAgent", Model)
    monkeypatch.setattr(WebSource, "fetch", fetch)
    result = await WebSource().collect(s, plan)
    assert [p['date'] for p in result['points']] == ['2024-02']
    assert result['raw']['conflicts']
    assert any('blocked' in w for w in result['warnings'])
