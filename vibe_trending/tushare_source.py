"""Evidence-preserving extraction from official MCP results, never LLM numbers."""
import hashlib
import json
import math
import re
from datetime import datetime, timezone

from .tushare_mcp import call_tool

PRICES = {'open': '元', 'high': '元', 'low': '元', 'close': '元', 'pre_close': '元',
          'pct_chg': '%', 'vol': '手', 'amount': '千元'}
PROFILES = {
    'daily': {'title': 'A股日行情', 'frequency': 'daily', 'date_field': 'trade_date', 'fields': PRICES},
    'fund_daily': {'title': 'ETF日行情', 'frequency': 'daily', 'date_field': 'trade_date', 'fields': PRICES},
    'index_daily': {'title': '指数日行情', 'frequency': 'daily', 'date_field': 'trade_date',
                    'fields': {**PRICES, **{key: '点' for key in ('open', 'high', 'low', 'close', 'pre_close')}}},
    'daily_basic': {'title': '股票每日指标', 'frequency': 'daily', 'date_field': 'trade_date',
                    'fields': {'close': '元', 'pe': '倍', 'pe_ttm': '倍', 'pb': '倍',
                               'turnover_rate': '%', 'total_mv': '万元', 'circ_mv': '万元'}},
    'fund_nav': {'title': '基金净值', 'frequency': 'daily', 'date_field': 'nav_date',
                 'fields': {'unit_nav': '元', 'accum_nav': '元', 'adj_nav': '元'}},
    'cn_cpi': {'title': '中国月度CPI', 'frequency': 'monthly', 'date_field': 'month',
               'fields': {key: '%' for key in ('nt_yoy', 'nt_mom', 'town_yoy', 'town_mom', 'cnt_yoy', 'cnt_mom')}},
    'cn_gdp': {'title': '中国年度GDP（Q4累计原值）', 'frequency': 'annual', 'date_field': 'quarter',
               'fields': {'gdp': '亿元', 'gdp_yoy': '%'}},
}


def specification(series):
    options = series.source_options
    api, field = options.get('api_name'), options.get('value_field')
    profile = PROFILES.get(api)
    if not profile or field not in profile['fields']:
        raise ValueError('Tushare 需要选择受支持的 api_name 和 value_field，不支持的指标请使用网页或其他数据源')
    if series.unit != profile['fields'][field] or series.frequency != profile['frequency']:
        raise ValueError(f'Tushare {api}.{field} 必须使用 {profile["frequency"]} 粒度及原单位 {profile["fields"][field]}')
    if api.startswith('cn_'):
        if series.country not in {'CHN', '中国'}:
            raise ValueError('该 Tushare 宏观接口仅提供中国数据')
    else:
        code = options.get('ts_code', '')
        if not re.fullmatch(r'\d{6}\.(SH|SZ|BJ|OF)', code):
            raise ValueError('Tushare 必须填写明确的完整证券代码，如 512480.SH，不可猜测证券')
        if code.endswith('.OF') and api != 'fund_nav':
            raise ValueError('场外基金代码只能用于基金净值，不能用于交易价格')
    return api, field, profile


def rows_from_response(raw):
    if raw.get('isError'):
        raise ValueError('Tushare MCP 返回查询错误，请检查接口权限和调用额度')
    data = raw.get('structuredContent')
    if data is None:
        blocks = [block['text'] for block in raw.get('content', []) if block.get('type') == 'text']
        if len(blocks) != 1:
            raise ValueError('Tushare MCP 未返回单一结构化数据响应')
        try:
            data = json.loads(blocks[0])
        except (ValueError, TypeError):
            raise ValueError('Tushare MCP 返回非JSON响应，请检查接口权限和调用额度') from None
    if isinstance(data, dict):
        if data.get('code', 0) != 0 or data.get('error'):
            raise ValueError('Tushare 查询被拒绝，请检查接口权限和调用额度')
        data = data.get('data', data)
        if isinstance(data, dict) and 'fields' in data and 'items' in data:
            fields = data['fields']
            if any(len(row) != len(fields) for row in data['items']):
                raise ValueError('Tushare 返回的字段和记录长度不匹配')
            data = [dict(zip(fields, row)) for row in data['items']]
    if not isinstance(data, list) or any(not isinstance(row, dict) for row in data):
        raise ValueError('Tushare 返回的数据结构不支持')
    return data


class TushareSource:
    async def collect(self, series, plan):
        api, field, profile = specification(series)
        stamp = datetime.now(timezone.utc).isoformat()
        url = 'https://api.tushare.pro/mcp/'
        responses, points = [], {}
        # Year-sized requests avoid upstream row caps and preserve each raw response.
        if plan.end_year - plan.start_year > 30:
            raise ValueError('Tushare 单次最多采集31年，请缩小区间')
        for year in range(plan.start_year, plan.end_year + 1):
            fields = [profile['date_field'], field]
            if api.startswith('cn_'):
                suffix = 'm' if api == 'cn_cpi' else 'q'
                bounds = (f'{year}01', f'{year}12') if suffix == 'm' else (f'{year}Q1', f'{year}Q4')
                arguments = {f'start_{suffix}': bounds[0], f'end_{suffix}': bounds[1], 'fields': fields}
            else:
                fields.insert(0, 'ts_code')
                arguments = {'ts_code': series.source_options['ts_code'], 'start_date': f'{year}0101',
                             'end_date': f'{year}1231', 'fields': fields}
            raw = await call_tool(api, arguments)
            rows = rows_from_response(raw)
            digest = hashlib.sha256(json.dumps(raw, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
            responses.append({'tool': api, 'arguments': arguments, 'response': raw, 'sha256': digest})
            for row in rows:
                if not api.startswith('cn_') and row.get('ts_code') != arguments['ts_code']:
                    raise ValueError('Tushare 返回其他证券的数据，拒绝混入序列')
                date = str(row.get(profile['date_field'], ''))
                if api == 'cn_gdp':
                    if not re.fullmatch(r'\d{4}Q[1-4]', date):
                        raise ValueError('Tushare 返回非法季度')
                    if not date.endswith('Q4'):
                        continue
                    date = date[:4]
                else:
                    fmt = '%Y%m' if api == 'cn_cpi' else '%Y%m%d'
                    if not re.fullmatch(r'\d{6}' if api == 'cn_cpi' else r'\d{8}', date):
                        raise ValueError('Tushare 返回非法日期')
                    date = datetime.strptime(date, fmt).strftime('%Y-%m' if api == 'cn_cpi' else '%Y-%m-%d')
                if int(date[:4]) != year:
                    raise ValueError('Tushare 返回区间外数据，拒绝混入口径')
                value = row.get(field)
                if value is None:
                    continue
                if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                    raise ValueError('Tushare 返回非法数值')
                if date in points and points[date]['value'] != value:
                    raise ValueError('Tushare 同日字段存在冲突，拒绝静默覆盖')
                points[date] = {'date': date, 'value': value, 'quality': 'source_verified', 'manual': False,
                                'source_url': url, 'collected_at': stamp, 'evidence_sha256': digest,
                                'quote': json.dumps(row, ensure_ascii=False), 'value_text': str(value)}
        if not points:
            raise ValueError('Tushare 在指定区间未返回可用数据，请检查证券、权限及口径')
        return {'source': 'tushare', 'points': sorted(points.values(), key=lambda p: p['date']),
                'raw': {'mcp_server': 'tushareMcp', 'requests': responses}, 'source_url': url,
                'collected_at': stamp, 'warnings': ['Tushare 原始字段，不转换单位；行情不复权，基金净值与交易价格不同。']}
