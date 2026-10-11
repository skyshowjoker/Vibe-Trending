import json

import pytest

from vibe_trending import tushare_source as source
from vibe_trending.models import Plan, SeriesPlan
from vibe_trending import app as application


def series(**updates):
    return SeriesPlan(name='半导体ETF', indicator='ETF收盘价', source='tushare', country='CHN',
                      frequency='daily', unit='元', source_options={
                          'api_name': 'fund_daily', 'ts_code': '512480.SH', 'value_field': 'close'}, **updates)


def response(rows):
    return {'content': [{'type': 'text', 'text': json.dumps(rows)}], 'isError': False}


@pytest.mark.asyncio
async def test_official_mcp_rows_and_year_batches(monkeypatch):
    calls = []
    async def call(name, args):
        calls.append((name, args))
        return response([{'ts_code': args['ts_code'], 'trade_date': args['start_date'][:4] + '0102', 'close': 0.79}])
    monkeypatch.setattr(source, 'call_tool', call)
    s = series()
    result = await source.TushareSource().collect(s, Plan(title='test', start_year=2023, end_year=2024, series=[s]))
    assert len(calls) == 2
    assert calls[0][0] == 'fund_daily'
    assert calls[0][1]['fields'] == ['ts_code', 'trade_date', 'close']
    assert [p['date'] for p in result['points']] == ['2023-01-02', '2024-01-02']
    assert result['raw']['mcp_server'] == 'tushareMcp'
    assert result['raw']['requests'][0]['response']['content']
    assert all('token=' not in p['source_url'] for p in result['points'])


@pytest.mark.asyncio
@pytest.mark.parametrize('row', [
    {'ts_code': 'OTHER.SH', 'trade_date': '20240102', 'close': 0.79},
    {'ts_code': '512480.SH', 'trade_date': '20230102', 'close': 0.79},
    {'ts_code': '512480.SH', 'trade_date': '20240102', 'close': float('nan')},
])
async def test_invalid_observations_rejected(monkeypatch, row):
    async def call(*args):
        return response([row])
    monkeypatch.setattr(source, 'call_tool', call)
    s = series()
    with pytest.raises(ValueError):
        await source.TushareSource().collect(s, Plan(title='test', start_year=2024, end_year=2024, series=[s]))


def test_units_codes_and_source_identity():
    s = series()
    assert source.specification(s)[0] == 'fund_daily'
    with pytest.raises(ValueError):
        source.specification(s.model_copy(update={'unit': '万元'}))
    with pytest.raises(ValueError):
        source.specification(s.model_copy(update={'source_options': {**s.source_options, 'ts_code': ''}}))
    other = s.model_copy(update={'source_options': {**s.source_options, 'ts_code': '159915.SZ'}})
    assert application.series_identity(s) != application.series_identity(other)


def test_permission_errors_and_tabular_response():
    with pytest.raises(ValueError, match='权限'):
        source.rows_from_response({'isError': True})
    with pytest.raises(ValueError, match='权限'):
        source.rows_from_response({'content': [{'type': 'text', 'text': 'permission denied'}]})
    assert source.rows_from_response({'structuredContent': {'code': 0, 'data': {
        'fields': ['close'], 'items': [[0.79]]}}}) == [{'close': 0.79}]


def test_private_token_redacted(monkeypatch):
    from vibe_trending import tushare_mcp
    url = 'https://api.tushare.pro/mcp/?token=test-private-credential'
    monkeypatch.setattr(tushare_mcp, 'endpoint', lambda: url)
    result = tushare_mcp.redact({'content': [{'text': 'failed ' + url}], 'token': 'test-private-credential'})
    assert 'test-private-credential' not in json.dumps(result)
    assert 'token=' not in json.dumps(result)


@pytest.mark.asyncio
async def test_annual_gdp_uses_q4_not_quarter_sum(monkeypatch):
    async def call(*args):
        return response([{'quarter': '2024Q1', 'gdp': 30}, {'quarter': '2024Q4', 'gdp': 130}])
    monkeypatch.setattr(source, 'call_tool', call)
    s = SeriesPlan(name='中国GDP', indicator='GDP', unit='亿元', source='tushare',
                   source_options={'api_name': 'cn_gdp', 'value_field': 'gdp'})
    result = await source.TushareSource().collect(s, Plan(title='test', start_year=2024, end_year=2024, series=[s]))
    assert [(p['date'], p['value']) for p in result['points']] == [('2024', 130)]
