"""Deterministic ETF daily close extraction from Eastmoney K-line JSON."""
import math
import re
from datetime import datetime, timezone

import httpx


def etf_code(series):
    if series.frequency != "daily" or "ETF" not in (series.name + series.indicator).upper() or "收盘" not in series.indicator:
        return None
    codes = set(re.findall(r"(?<!\d)(?:5\d{5}|15\d{4})(?!\d)", series.query + " " + series.indicator))
    return next(iter(codes)) if len(codes) == 1 else None


class EtfHistorySource:
    async def collect(self, series, plan):
        code = etf_code(series)
        if not code or series.unit != "元":
            raise ValueError("ETF 日收盘价需要明确的沪深基金代码及单位元")
        url = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
        params = {"secid": f"{1 if code.startswith('5') else 0}.{code}", "klt": "101", "fqt": "0",
                  "beg": f"{plan.start_year}0101", "end": f"{plan.end_year}1231",
                  "fields1": "f1,f2,f3,f4,f5,f6", "fields2": "f51,f52,f53,f54,f55,f56,f57"}
        async with httpx.AsyncClient(timeout=40) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            raw = response.json()
        data = raw.get("data") or {}
        if raw.get("rc") != 0 or data.get("code") != code or not data.get("klines"):
            raise ValueError(f"ETF {code} 接口未返回匹配的历史行情")
        points, stamp = [], datetime.now(timezone.utc).isoformat()
        for line in data["klines"]:
            fields = line.split(",")
            date = fields[0]
            datetime.strptime(date, "%Y-%m-%d")
            value = float(fields[2])
            if not math.isfinite(value):
                raise ValueError("行情接口返回了非法收盘价")
            if plan.start_year <= int(date[:4]) <= plan.end_year:
                points.append({"date": date, "value": value, "source_url": str(response.url),
                               "collected_at": stamp, "quality": "source_verified", "manual": False,
                               "quote": line, "value_text": fields[2]})
        if not points:
            raise ValueError(f"ETF {code} 在指定区间没有历史行情")
        return {"points": sorted(points, key=lambda p: p['date']), "raw": raw,
                "source": "eastmoney", "source_url": str(response.url), "collected_at": stamp,
                "warnings": [f"实际证券：{data.get('name')}（{code}）；日收盘价，人民币元，不复权，非基金净值。"]}
