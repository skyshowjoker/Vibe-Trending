"""Private configuration and transport for the official Tushare MCP service."""
import asyncio
import logging
import os
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from dotenv import dotenv_values
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


def endpoint():
    path = Path(__file__).resolve().parents[1] / '.data/tushare.env'
    url = os.getenv('TUSHARE_MCP_URL') or dotenv_values(path).get('TUSHARE_MCP_URL')
    if not url:
        raise ValueError('请配置 TUSHARE_MCP_URL')
    parsed = urlparse(url)
    if parsed.scheme != 'https' or parsed.hostname != 'api.tushare.pro':
        raise ValueError('TUSHARE_MCP_URL 必须使用官方 HTTPS 服务')
    return url


def redact(value):
    if isinstance(value, dict):
        return {key: redact(item) for key, item in value.items()}
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, str):
        url = endpoint()
        value = value.replace(url, 'https://api.tushare.pro/mcp/')
        for token in parse_qs(urlparse(url).query).get('token', []):
            value = value.replace(token, '[REDACTED]')
    return value


async def tools_list():
    logging.getLogger('httpx').setLevel(logging.WARNING)
    try:
        async with asyncio.timeout(45):
            async with streamable_http_client(endpoint()) as (reader, writer, _):
                async with ClientSession(reader, writer) as session:
                    await session.initialize()
                    result = await session.list_tools()
                    return [tool.model_dump() for tool in result.tools]
    except Exception:
        raise RuntimeError('Tushare MCP 连接失败，请检查凭据、网络及服务状态') from None


async def call_tool(name, arguments):
    logging.getLogger('httpx').setLevel(logging.WARNING)
    try:
        async with asyncio.timeout(60):
            async with streamable_http_client(endpoint()) as (reader, writer, _):
                async with ClientSession(reader, writer) as session:
                    await session.initialize()
                    result = await session.call_tool(name, arguments)
                    return redact(result.model_dump(by_alias=True, exclude_none=True))
    except Exception:
        raise RuntimeError('Tushare MCP 查询失败，请检查网络、接口权限及频率限制') from None


if __name__ == '__main__':
    import json
    discovered = asyncio.run(tools_list())
    print(json.dumps({'count': len(discovered), 'tools': [t for t in discovered if t['name'] in
        {'daily', 'fund_daily', 'index_daily', 'cn_cpi', 'cn_gdp', 'fund_nav'}]}, ensure_ascii=False))
