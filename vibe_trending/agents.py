"""The only module aware of an Agent kernel's transport protocol."""
import asyncio
import importlib
import json
import os
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Protocol

import httpx
import websockets
import yaml
from dotenv import dotenv_values

from .models import Plan, SeriesPlan

CATALOG = [
    {"id": "NY.GDP.MKTP.CD", "name": "GDP", "unit": "美元"},
    {"id": "NY.GDP.PCAP.CD", "name": "人均 GDP", "unit": "美元/人"},
    {"id": "SP.POP.TOTL", "name": "人口", "unit": "人"},
    {"id": "FP.CPI.TOTL.ZG", "name": "通胀率", "unit": "%"},
    {"id": "SL.UEM.TOTL.ZS", "name": "失业率", "unit": "%"},
    {"id": "IT.NET.USER.ZS", "name": "互联网普及率", "unit": "%"},
    {"id": "EN.ATM.CO2E.PC", "name": "人均碳排放", "unit": "吨/人"},
]
COUNTRIES = {"中国": "CHN", "美国": "USA", "日本": "JPN", "德国": "DEU", "印度": "IND", "英国": "GBR", "全球": "WLD"}


def tushare_instruction():
    from .tushare_source import PROFILES
    return (
        '金融数据以Tushare为主要来源，覆盖以下接口时默认source=tushare，除非用户明确指定其他来源。'
        'source_options必须包含api_name、value_field，证券接口还必须包含完整ts_code。'
        'ETF收盘价用fund_daily.close，股票用daily.close，指数用index_daily.close，基金净值用fund_nav.unit_nav；'
        '禁止将净值与市场价格混淆。用户未提供证券代码时返回error要求补充，不猜证券。'
        '示例512480 ETF代码为512480.SH，159915 ETF代码为159915.SZ。'
        '中国GDP人民币亿元年度用cn_gdp.gdp（仅Q4累计值）；中国CPI月度同比用cn_cpi.nt_yoy，单位%。'
        '全球或美元GDP等未覆盖需求仍用World Bank或网页，不换单位、不改口径。'
        '编辑已有策略时保留未要求修改的序列和来源，不自动迁移历史数据。'
        f'Tushare可保存字段及原单位、粒度：{json.dumps(PROFILES, ensure_ascii=False)}。'
    )


class AgentBackend(Protocol):
    async def plan(self, prompt: str) -> Plan: ...


class DeepSeekAgent:
    """Reuse the existing model settings without copying credentials."""

    def __init__(self):
        path = Path(os.getenv("VIBE_MODEL_CONFIG", "~/.jiuwenswarm/config/config.yaml")).expanduser()
        config = yaml.safe_load(path.read_text(encoding="utf-8"))
        candidates = config["models"]["defaults"]
        self.settings = next(item["model_client_config"] for item in candidates
                             if "deepseek" in item["model_client_config"].get("model_name", "").lower())
        env = {**dotenv_values(path.parent / ".env"), **os.environ}
        def resolve(value):
            return re.sub(r"\$\{([A-Z_][A-Z_0-9]*)(?::-([^}]*))?\}",
                          lambda m: env.get(m[1]) or m[2] or "", str(value))
        self.model = resolve(self.settings["model_name"])
        self.key = resolve(self.settings["api_key"])
        self.base = resolve(self.settings["api_base"]).rstrip("/")
        if not self.key or not self.base.startswith("https://"):
            raise ValueError("DeepSeek 配置缺少凭据或 HTTPS 接口地址")

    async def plan(self, prompt: str) -> Plan:
        instruction = (
            "你是 Vibe Trending 策略规划器。只返回 JSON，不生成观测数值。" +
            tushare_instruction() +
            "Tushare未覆盖但匹配以下指标时使用 World Bank 年度数据。其他需求用 source=web，indicator为指标名称，"
            "query为精确搜索词，country为地区或对象，unit为要求的原文单位，frequency为annual/monthly/daily。"
            "用户给的网址原样放入 urls，不得编造网址。web允许任意主题和地区。不能把新闻篇数当销量。"
            "网页采集不做单位换算，只接收原文单位一致的数据，notes不要建议换算或插值。"
            f"Schema: {json.dumps(Plan.model_json_schema(), ensure_ascii=False)}。"
            f"指标: {json.dumps(CATALOG, ensure_ascii=False)}。"
            f"国家: {json.dumps(COUNTRIES, ensure_ascii=False)}。"
            f"当前年份: {datetime.now().year}。用中文填写标题和说明。"
        )
        result = await self.json_call(instruction, prompt)
        if result.get("error"):
            raise ValueError(str(result["error"]))
        plan = Plan.model_validate(result)
        for s in plan.series:
            if s.source == 'tushare':
                from .tushare_source import specification
                specification(s)
            elif s.source == "worldbank":
                if s.indicator not in {item["id"] for item in CATALOG} or s.country not in COUNTRIES.values():
                    raise ValueError("模型返回了不支持的 World Bank 指标或地区")
            elif s.source not in {"web", "eastmoney"} or (not s.query and not s.urls):
                raise ValueError("网页策略缺少搜索词或网址")
        return plan

    async def json_call(self, instruction: str, prompt: str) -> dict:
        async with httpx.AsyncClient(timeout=180) as client:
            response = await client.post(self.base + "/chat/completions",
                headers={"Authorization": f"Bearer {self.key}"},
                json={"model": self.model, "messages": [
                    {"role": "system", "content": instruction},
                    {"role": "user", "content": prompt}],
                    "stream": False, "response_format": {"type": "json_object"}})
            if response.is_error:
                raise RuntimeError(f"DeepSeek 请求失败，HTTP {response.status_code}")
            result = json.loads(response.json()["choices"][0]["message"]["content"])
            return result


class RuleAgent:
    async def plan(self, prompt: str) -> Plan:
        countries = [(name, code) for name, code in COUNTRIES.items() if name in prompt] or [("中国", "CHN")]
        indicators = [item for item in CATALOG if item["name"].lower() in prompt.lower()]
        if "人均" in prompt:
            indicators = [item for item in indicators if item["name"] != "GDP"]
        if not indicators:
            raise ValueError("规则模式未识别指标，请选择 GDP、人口、通胀率、失业率或互联网普及率；更多意图请连接 JiuwenSwarm。")
        years = [int(year) for year in re.findall(r"(?:19|20)\d{2}", prompt)]
        end = max(years) if len(years) > 1 else datetime.now().year - 1
        start = min(years) if years else end - 10
        return Plan(title=prompt[:80], start_year=start, end_year=end, series=[SeriesPlan(name=f"{name} · {item['name']}", indicator=item["id"], country=code, unit=item["unit"]) for name, code in countries for item in indicators])


class JiuwenSwarmAgent:
    def __init__(self):
        self.url = os.getenv("JIUWENSWARM_AGENT_URL", "ws://127.0.0.1:18092")

    async def plan(self, prompt: str) -> Plan:
        instruction = (
            "你是 Vibe Trending 的策略规划 Agent。仅返回符合以下 schema 的 JSON，不要调用工具，不要生成观测数值。"
            + tushare_instruction() +
            f"Schema: {json.dumps(Plan.model_json_schema(), ensure_ascii=False)}。"
            f"World Bank 年度指标: {json.dumps(CATALOG, ensure_ascii=False)}。其他需求使用 source=web，"
            "query为搜索词，urls仅包含用户给的网址，indicator为指标名，frequency为annual/monthly/daily。"
            f"国家: {json.dumps(COUNTRIES, ensure_ascii=False)}。无法满足时明确报错，不要偷换指标。用户需求: {prompt}"
        )
        request_id = uuid.uuid4().hex
        async with asyncio.timeout(180):
            async with websockets.connect(self.url, max_size=8 * 1024 * 1024) as ws:
                await ws.recv()
                await ws.send(json.dumps({"request_id": request_id, "channel_id": "web", "session_id": f"vibetrending_{request_id}", "params": {"query": instruction, "content": instruction, "mode": "agent"}, "is_stream": False}))
                while True:
                    response = json.loads(await ws.recv())
                    if response.get("request_id") != request_id:
                        continue
                    if response.get("ok") is False or response.get("status") == "failed":
                        raise RuntimeError(str(response.get("error") or response))
                    body = response.get("payload") or response.get("body") or {}
                    body = body.get("result", body)
                    text = body.get("content") or body.get("output") or body.get("text")
                    if isinstance(text, str):
                        match = re.search(r"\{.*\}", text, re.S)
                        if not match:
                            raise ValueError("Agent 未返回有效策略 JSON: " + text[:300])
                        return Plan.model_validate_json(match.group())
                    raise ValueError("JiuwenSwarm 响应缺少策略文本")


def load_agent() -> tuple[str, AgentBackend]:
    name = os.getenv("VIBE_AGENT", "jiuwenswarm")
    if name == "rules":
        return name, RuleAgent()
    if name == "jiuwenswarm":
        return name, JiuwenSwarmAgent()
    if name == "deepseek":
        return name, DeepSeekAgent()
    module, cls = name.split(":", 1)
    return name, getattr(importlib.import_module(module), cls)()
