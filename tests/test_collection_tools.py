import asyncio
import json

import pytest

from vibe_trending import collection_tools as tools
from vibe_trending.models import Plan, SeriesPlan


def operation():
    series = SeriesPlan(name='销量', indicator='销量', source='web', unit='万辆')
    return tools.create_job(tools.JobInput(series=series, plan=Plan(
        title='test', start_year=2024, end_year=2024, series=[series])))['operation_id']


def test_agent_must_submit_tool_evidence():
    key = operation()
    try:
        with pytest.raises(ValueError, match='没有采集证据'):
            asyncio.run(tools.finish_collection(key, []))
        with pytest.raises(KeyError):
            asyncio.run(tools.finish_collection(key, ['invented']))
        assert tools.get_job(key)['result'] is None
    finally:
        tools.delete_job(key)


def test_web_candidates_validated_and_trace_saved():
    key = operation()
    url = 'https://example.org/data'
    text = '2024年汽车销量为3143.6万辆，产销保持稳定。'
    tools.job(key)['pages'][url] = {'url': url, 'text': text, 'body': text, 'sha256': 'hash'}
    try:
        good = {'date': '2024', 'value': 3143.6, 'value_text': '3143.6', 'unit': '万辆', 'quote': text}
        bad = {**good, 'value': 999}
        result = asyncio.run(tools.submit_web_points(key, url, json.dumps([good, bad])))
        assert result['count'] == 1
        assert len(result['warnings']) == 1
        asyncio.run(tools.finish_collection(key, [result['artifact_id']]))
        saved = tools.get_job(key)['result']
        assert saved['collector'] == 'jiuwenswarm'
        assert saved['points'][0]['value'] == 3143.6
        assert [item['tool'] for item in saved['raw']['agent_tools']] == ['submit_web_points', 'finish_collection']
        assert saved['raw']['evidence'][0]['pages'][0]['body'] == text
    finally:
        tools.delete_job(key)


def test_repeated_spec_is_bounded():
    key = operation()
    try:
        for _ in range(3):
            asyncio.run(tools.collection_spec(key))
        with pytest.raises(ValueError, match='采集预算'):
            asyncio.run(tools.collection_spec(key))
        assert tools.get_job(key)['error']
    finally:
        tools.delete_job(key)


def test_failed_page_reads_consume_budget(monkeypatch):
    async def fetch(self, url):
        raise ValueError('no readable content')
    monkeypatch.setattr(tools.WebSource, 'fetch', fetch)
    key = operation()
    try:
        for _ in range(8):
            with pytest.raises(ValueError, match='no readable content'):
                asyncio.run(tools.read_source(key, 'https://example.org'))
        with pytest.raises(ValueError, match='采集预算'):
            asyncio.run(tools.read_source(key, 'https://example.org'))
        assert len(tools.get_job(key)['trace']) == 9
    finally:
        tools.delete_job(key)


def test_agent_can_report_no_evidence():
    key = operation()
    try:
        asyncio.run(tools.fail_collection(key, '页面需要登录'))
        assert '页面需要登录' in tools.get_job(key)['error']
        assert tools.get_job(key)['result'] is None
        with pytest.raises(ValueError, match='页面需要登录'):
            asyncio.run(tools.search_sources(key, 'retry'))
    finally:
        tools.delete_job(key)


def test_double_escaped_table_newlines_keep_original_quote():
    key = operation()
    text = '| 时间 | 就业人员(万人) | \n| 2015年 | 350 | \n| 2024年 | 455 |'
    series, plan = tools.job(key)['series'], tools.job(key)['plan']
    candidate = {'date': '2024', 'value': 455, 'value_text': '455', 'unit': '万人',
                 'quote': text.replace('\n', '\\n')}
    series.unit = '万人'
    try:
        assert tools.validate_point(candidate, text, series, plan)['quote'] == text
        with pytest.raises(ValueError):
            tools.validate_point({**candidate, 'quote': candidate['quote'].replace('350', '351')}, text, series, plan)
        with pytest.raises(ValueError):
            tools.validate_point({**candidate, 'value': 999}, text, series, plan)
    finally:
        tools.delete_job(key)
