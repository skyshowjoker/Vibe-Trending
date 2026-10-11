import importlib
import os
from datetime import datetime, timezone

import httpx

from .models import Plan, SeriesPlan


class WorldBankSource:
    async def collect(self, series: SeriesPlan, plan: Plan) -> dict:
        url = f"https://api.worldbank.org/v2/country/{series.country}/indicator/{series.indicator}"
        async with httpx.AsyncClient(timeout=45, follow_redirects=True) as client:
            response = await client.get(url, params={"format": "json", "date": f"{plan.start_year}:{plan.end_year}", "per_page": "1000"})
            response.raise_for_status()
            raw = response.json()
        if not isinstance(raw, list) or len(raw) < 2 or not isinstance(raw[1], list):
            raise ValueError("World Bank 未返回数据，请检查指标和国家代码")
        now = datetime.now(timezone.utc).isoformat()
        points = [{"date": item["date"], "value": item["value"], "quality": "source_verified", "manual": False, "source_url": str(response.url), "collected_at": now} for item in raw[1] if item.get("value") is not None]
        if not points:
            raise ValueError(f"{series.name} 在指定区间无可用数据")
        return {"points": sorted(points, key=lambda point: point["date"]), "raw": raw, "source_url": str(response.url), "collected_at": now}


def load_sources() -> dict:
    from .web_source import WebSource
    from .market_source import EtfHistorySource
    from .tushare_source import TushareSource
    sources = {"tushare": TushareSource(), "worldbank": WorldBankSource(), "web": WebSource(), "eastmoney": EtfHistorySource()}
    for name, path in __import__("json").loads(os.getenv("VIBE_SOURCE_PLUGINS", "{}")).items():
        module, cls = path.split(":", 1)
        sources[name] = getattr(importlib.import_module(module), cls)()
    return sources
