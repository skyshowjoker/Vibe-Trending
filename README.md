# Vibe Trending

独立的本地单用户趋势研究 MVP。自然语言策略确认、World Bank 与公开网页数据采集、来源存证、趋势图对比、人工编辑、版本回滚、定期更新、CSV/PNG 导出。

## 启动

```bash
cd /Users/mac/devRepo/vibe-trending
python3.11 -m venv .venv311
.venv311/bin/pip install -e '.[test]'
# 隔离安装与当前 JiuwenSwarm 仓库匹配的内核，不覆盖其虚拟环境
uv pip install --python ../jiuwenswarm/.venv/bin/python --target .runtime/jiuwen-core --no-deps openjiuwen==0.1.15.post3
# 分别在三个终端运行
.venv311/bin/uvicorn vibe_trending.collection_tools:app --host 127.0.0.1 --port 8901
.venv311/bin/python -m vibe_trending.start_collection_kernel
VIBE_AGENT=deepseek VIBE_COLLECTOR=jiuwenswarm .venv311/bin/uvicorn vibe_trending.app:app --host 127.0.0.1 --port 8088
```

访问 http://localhost:8088 。JiuwenSwarm 可从其仓库使用 `jiuwenswarm-start dev` 启动。
默认数据库 `.data/vibe.db`，可通过 `VIBE_DB` 改路径。
DeepSeek 适配器默认读取 `~/.jiuwenswarm/config/config.yaml` 和同目录 `.env`，
可通过 `VIBE_MODEL_CONFIG` 指定配置文件；修改模型配置后重启本服务。
策略生成直接调用 DeepSeek；数据采集默认由真实 JiuwenSwarm AgentServer（18093）执行，复用同一 DeepSeek 模型。采集内核独立工作目录为 `.data/jiuwen-collector`，不会启动原项目的三方频道。

## Tushare 主要数据源

金融需求默认优先通过用户配置的官方 Tushare MCP 采集，World Bank、网页和东方财富保留。已有项目不会自动迁移或改写数值，可通过 Vibe edit 显式换源。配置 `TUSHARE_MCP_URL` 环境变量，或本机 `.data/tushare.env`（权限600）；URL中的Token不进入策略、页面、来源链接、原始证据或内核配置。

链路为 JiuwenSwarm Agent → 本地 `fetch_structured(source=tushare)` → 官方 Tushare MCP → 原始JSON字段校验 → artifact → Agent提交。不是直接使用Tushare HTTP数据API，也不把254个远端工具全部注入模型上下文。

目前接入7个接口：A股日行情 `daily`、ETF日行情 `fund_daily`、指数行情 `index_daily`、每日指标 `daily_basic`、基金净值 `fund_nav`、中国月度CPI `cn_cpi`、年度GDP `cn_gdp`（仅Q4累计原值，不累加季度）。可选字段、原单位和粒度以页面接口选择器为准。其他远端工具暂未映射为趋势序列，不代表不可用；后续在 `tushare_source.PROFILES` 及解析器扩展。权限、积分和调用频率限制由Tushare服务决定，失败明确报错，不静默换源或换口径。

策略的 `source_options` 保存 `api_name`、`value_field` 和证券接口的 `ts_code`；例如 `fund_daily / close / 512480.SH`，单位元、日度、不复权。按年分段获取并保存每次原始MCP响应及SHA256，校验证券、日期、数值和单位，拒绝冲突。单次最多31年。参考 [官方MCP配置](https://tushare.pro/document/1?doc_id=463)、[CPI字段](https://tushare.pro/document/41?doc_id=228)、[GDP字段](https://tushare.pro/document/2?doc_id=227)。

已有项目点击 `Vibe edit`，描述新增/调整序列或数据源，预览完整策略及增删差异后确认。默认应用后采集，也可取消勾选仅保存策略。未改变采集口径的历史值及人工确认值保留；替换来源、查询、单位或粒度会作为新口径处理，旧数据保留在版本中。支持恢复版本，应用前校验项目修订号；期间有其他更新时需重新生成方案。项目最多 8 条序列。

## 内核插件

业务层只依赖 `AgentBackend.plan(prompt) -> Plan`。JiuwenSwarm 使用 WebSocket 适配器，核心业务无需安装其 Python 包；独立部署或升级内核无需改变业务层。

```python
from vibe_trending.models import Plan
class MyAgent:
    async def plan(self, prompt: str) -> Plan:
        ...
```

使用 `VIBE_AGENT=my_package.agent:MyAgent` 替换规划器。

采集层依赖 `CollectionBackend.collect(series, plan) -> dict`，使用 `VIBE_COLLECTOR=my_package.collector:MyCollector` 替换内核。默认 JiuwenSwarm 通过 MCP 自主调用搜索、网页读取、结构化接口、候选点校验和提交工具；正式数值只能来自工具产物，不能来自 Agent 最终文字。原始证据中保存 `agent_tools` 调用轨迹。内核不可用会明确失败，不静默退回直接采集。仅测试或显式兼容运行时可设置 `VIBE_COLLECTOR=direct`。

每条序列最多搜索 6 次、网页读取 8 次（失败也计数）、结构化接口 3 次；预算耗尽立即结束。缺少证据时 Agent 可主动调用 `fail_collection`。无须覆盖全部年份才提交，有效点可保留，缺失点留空。失败任务保存工具轨迹；完成、失败或超时后，通过 `chat.interrupt` 取消内核任务，再释放临时操作，避免后台继续搜索已删除的任务。

连接可通过 `VIBE_COLLECTION_AGENT_URL` 和 `VIBE_COLLECTION_TOOLS_URL` 配置；工具地址必须同时提供给业务进程和内核启动器。采集单序列超时 360 秒，工具任务临时存于内存，进程重启会丢失未完成操作。启动器默认使用相邻 JiuwenSwarm 仓库和其虚拟环境，可用 `VIBE_JIUWENSWARM_ROOT` / `VIBE_JIUWENSWARM_PYTHON` 指定。该轻量接入是本地单用户 MVP，不是生产多租户隔离方案。

数据源实现 `async collect(series: SeriesPlan, plan: Plan) -> dict`，返回 `points/raw/source_url/collected_at`。
配置 `VIBE_SOURCE_PLUGINS='{"custom":"my_package.source:CustomSource"}'` 注册。

## MVP 范围与限制

- World Bank 提供 GDP、人口、通胀、失业、互联网等年度指标。
- 沪深 ETF 日收盘价支持东方财富结构化 K 线接口：指定唯一六位代码，单位元，不复权；保留实际证券名称、原始行情 JSON 和数据字段。已有 web 策略中带唯一 ETF 代码的日收盘价查询自动使用此接口。不能用收盘价替代净值或复权收益率；外部接口可能限流或变更。
- `web` 支持任意主题的公开 HTML/文本/JSON 网页，搜索发现最多 5 个链接，或使用最多 8 个指定网址。通过 DeepSeek 提取年度/月度/日度数字；正文截取前 24000 字符，每页上限 2MB。搜索依赖外部引擎可用性，失败时可改为指定网址。
- 网页数据点必须在正文中逐字匹配引句、数字、单位及日期，保存原文、SHA256、引句和链接；标记 `evidence_matched`，不等于语义或事实已验证，仍需人工核对指标口径。不同来源同日不同值拒绝纳入；缺少证据不会补造。当前严格引句检查可能拒绝跨行表头、单位换算等真实数据，属于有意的保守限制。
- 示例需求：`搜索中国2024年月度汽车销量，单位万辆`；也可以在需求里给出来源网址，随后在策略中编辑搜索词、单位、粒度和网址。
- 不支持登录/验证码绕过、JavaScript 渲染、PDF/图片 OCR、付费内容、全站无限爬取；不保证任意网站都能获取。只允许公开网络地址，不允许本机和内网。网页内容作为非可信数据，不执行网页指令。
- 每个正式数据点带来源 URL、采集时间、质量状态；保存原始 JSON 或网页正文及失败/冲突记录。无有效数据时任务失败，未进入正式数据集。
- 更新只追加新年份，保留所有已存历史数值及人工确认值；需要更新覆盖区间时重新建立策略。
- 每日、每周一、每月 1 日按时区运行。失败记录原因，连续失败 3 次暂停。进程停止期间不执行任务，重启后补执行到期任务一次。
- 版本为完整项目快照，支持回滚；数据修改记录前后值与原因。
- 对比展示单位、地区、频率差异，标准化是显式选择；不自动转换原始数据。
- 当前是本机单用户应用，绑定 localhost。未实现多用户身份、配额、批量 CSV 导入、数据表排序、序列元数据编辑、完整图表标注或任务有限重试；属于后续版本。
- 数据源可访问性在采集时由 HTTP 状态验证，历史来源链接后续可能失效。

## 验证

界面支持项目搜索与上次项目恢复、采集状态与错误反馈、图表悬停读数、50 条分页、日期筛选与排序、原始证据展开、删除/恢复确认以及移动端布局。界面显示时间使用浏览器本地时区，数据日期保留原始口径。当前仍是本地单用户 MVP，界面改进不等于多用户、权限、运维与商业部署能力已经完善。

```bash
.venv311/bin/python -m pytest -q
```

架构：页面 → FastAPI → CollectionBackend → JiuwenSwarm Agent → MCP 采集工具 → 校验证据 → SQLite 版本。规划器与采集内核可以分别替换。
