import httpx
import pytest

from vibe_trending.market_source import EtfHistorySource, etf_code
from vibe_trending.models import Plan, SeriesPlan


def test_distinct_etf_series_identity():
    from vibe_trending.app import series_identity
    first = SeriesPlan(name="ETF", indicator="ETF收盘价", source="web", query="512480", frequency="daily", unit="元")
    second = first.model_copy(update={"query": "512880"})
    assert series_identity(first) != series_identity(second)


@pytest.mark.asyncio
async def test_etf_close_field_and_evidence(monkeypatch):
    s = SeriesPlan(name="半导体ETF", indicator="ETF收盘价", source="web", query="512480", frequency="daily", unit="元")
    assert etf_code(s) == "512480"
    original = httpx.AsyncClient
    def handler(request):
        assert request.url.params['secid'] == '1.512480'
        assert request.url.params['fqt'] == '0'
        return httpx.Response(200, json={"rc": 0, "data": {"code": "512480", "name": "半导体ETF", "klines": ["2024-01-02,1.1,1.2,1.3,1.0,100,200"]}})
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: original(transport=httpx.MockTransport(handler), **kw))
    result = await EtfHistorySource().collect(s, Plan(title="ETF", start_year=2024, end_year=2024, series=[s]))
    assert result['points'][0]['value'] == 1.2
    assert result['points'][0]['source_url'].startswith('https://')
    assert result['raw']['data']['code'] == '512480'
    s.query = '512480 512880'
    assert etf_code(s) is None
