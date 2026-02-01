# AI-Quant System (US Sentiment Auto-Invest) — agent.md

## 0) 角色与目标
你是一位精通 Python 的量化交易架构师与工程负责人。请在低功耗 Linux 服务器（N100/NAS）上构建一个全自动美股情绪量化交易系统（AI-Quant System）。

核心流程（每日定时任务）：
1) 抓取新闻与社媒标题（RSS + Reddit）
2) 调用 DeepSeek V3 API（通过 openai SDK，兼容 OpenAI 格式）做清洗与情绪打分
3) 写入 PostgreSQL（Docker）
4) 生成交易信号（Top1：分数最高且无风险标签）
5) 通过 IBKR（ib_insync，AsyncIO）执行碎股定投（默认 dry_run=True）

## 1) 技术栈硬性约束
- Python 3.10+（强制 Type Hints；所有 public function/方法必须标注类型）
- AI：DeepSeek V3 API（openai SDK：OpenAI(base_url="https://api.deepseek.com")）
- 交易：Interactive Brokers（ib_insync，必须 AsyncIO）
- DB：PostgreSQL 15（Docker 部署）+ SQLAlchemy ORM（建议用 Async engine + asyncpg）
- Infra：Docker Compose
- 核心库：feedparser、praw、tenacity、loguru
- 设计目标：稳定、低资源、可恢复、可观测（日志）

## 2) 安全原则（必须遵守）
### 2.1 交易安全
- 默认 DRY_RUN=true：任何情况下只记录日志，严禁真实下单
- 只有当用户明确设置 DRY_RUN=false 才允许下真实订单
- 下单前必须做价格与数量校验：price>0、qty>0、qty合理（例如 >1e-6）
- 交易失败要记录详细日志（ticker、amount、price、order status）
- TRADING_MODE 强制 paper（镜像环境变量）

### 2.2 AI 输出安全
- DeepSeek 返回必须是“纯 JSON”
- 若输出无法解析/数组长度不匹配：跳过该批次（不得写入脏信号）
- sentiment 范围强制裁剪到 [-1, 1]
- ticker 提取不明确必须为 null（禁止猜测）

### 2.3 超时与稳定性
- DeepSeek API client 必须设置 timeout（建议 20~30s）
- 使用 tenacity 实现指数退避重试（建议最多 4 次）
- 批处理：每 10-20 条标题合并一次调用（节省成本、降低失败概率）
- 任何外部依赖（RSS/Reddit/AI/IB）失败都不得导致整个系统崩溃；应降级继续（例如：AI 失败则不交易）

## 3) 目录结构（必须创建）
repo_root/
- docker-compose.yml
- .env.example
- app/
  - __init__.py
  - main.py
  - collectors/
    - __init__.py
    - rss_collector.py
    - reddit_collector.py
  - processors/
    - __init__.py
    - ai_analyzer.py
  - db/
    - __init__.py
    - models.py
    - session.py
  - broker/
    - __init__.py
    - executor.py

（允许添加：config/、scripts/、README.md，但不要引入复杂框架）

## 4) 模块需求与接口契约（按文件实现）
### 4.1 app/collectors/rss_collector.py
目标：从 Yahoo Finance、CNBC 等 RSS 抓取标题与链接，输出 RawNews 待写入对象。

要求：
- 使用 feedparser
- 去重：基于 url 或 title（内存集合）
- 输出结构统一：source、raw_title、url、fetched_at(UTC)

接口建议：
- class RSSCollector:
  - def __init__(self, sources: list[RSSSource]) -> None
  - def fetch(self) -> list[RawNewsIn]  # RawNewsIn 为内部 dataclass/TypedDict 均可

### 4.2 app/collectors/reddit_collector.py
目标：抓取 r/stocks、r/investing 热门帖子标题（hot/top/new任选其一，建议 hot），输出 RawNews 待写入对象。

要求：
- 使用 praw
- 用 .env 提供：REDDIT_CLIENT_ID、REDDIT_CLIENT_SECRET、REDDIT_USER_AGENT
- 去重：基于 url 或 permalink 或 title
- 输出结构统一同 RSS

接口建议：
- class RedditCollector:
  - def __init__(self, subreddits: list[str], limit: int = 50) -> None
  - def fetch(self) -> list[RawNewsIn]

### 4.3 app/processors/ai_analyzer.py
目标：系统“大脑”。不使用本地 NLP，全部通过 DeepSeek API。

实现要求：
- 使用 openai SDK：OpenAI(api_key=..., base_url="https://api.deepseek.com")
- 批处理：每 10-20 条标题组成一个 prompt
- 必须要求 DeepSeek 返回“严格 JSON 数组”，长度与输入一致
- 返回字段（每条）：
  - ticker: "AAPL" 或 null
  - sentiment: float [-1,1]
  - summary: 一句话中文摘要（<=30字）
  - risk_tags: list[str]（如 财报/诉讼/监管/并购/停牌/做空报告）
- 防超时策略：
  - OpenAI client 设置 timeout
  - tenacity 指数退避重试
  - 若解析失败：跳过该批次，不写库，不交易
- 强制类型校验与裁剪：
  - sentiment 非法则置 0
  - ticker 不符合格式则置 null
  - risk_tags 非 list 则置 []

接口建议：
- dataclass AnalyzedItem(ticker: str|None, sentiment: float, summary: str, risk_tags: list[str])
- class AIAnalyzer:
  - def __init__(self, api_key: str, batch_size: int = 15, timeout_s: int = 25) -> None
  - def analyze_titles(self, titles: list[str]) -> list[AnalyzedItem]

### 4.4 app/db/models.py
目标：SQLAlchemy ORM 定义两张表：

RawNews:
- id (pk)
- source (str)
- raw_title (text)
- url (unique)
- fetched_at (UTC timestamptz)

SentimentSignal:
- id (pk)
- ticker (nullable str, index)
- score (float)
- risk_tags (array[str] 或 json)
- ai_summary (text)
- created_at (UTC timestamptz, index)

要求：
- url 必须 unique（用 DB 兜底去重）
- created_at/fetched_at 必须 UTC

### 4.5 app/db/session.py
目标：创建 AsyncEngine + AsyncSession maker（推荐 asyncpg）。

要求：
- DATABASE_URL 从环境变量读取（示例见 .env.example）
- 提供 init_db() 创建表（可简单 create_all）

### 4.6 app/broker/executor.py
目标：系统“手”。通过 ib_insync 异步连接 IB Gateway，并按金额碎股定投下单。

约束：
- 必须 AsyncIO：connectAsync / reqTickersAsync
- 连接：Host=ib-gateway, Port=4001
- __init__ 接收 dry_run: bool
  - dry_run=True：只记录日志“模拟买入 $40 AAPL”，严禁下单
  - dry_run=False：真实下单
- 碎股逻辑：
  - 获取最新价格 price（snapshot）
  - qty = amount_usd / price
  - 下 MarketOrder("BUY", qty)
- 必须有异常处理与日志（含 price、qty、orderStatus）

接口建议：
- class IBExecutor:
  - async def connect(self) -> None / async context manager
  - async def buy_fractional_by_amount(self, ticker: str, amount_usd: float) -> None

### 4.7 app/main.py
目标：主程序编排（每日任务入口）。

流程（必须按顺序）：
1) Collectors 抓取数据（RSS + Reddit）
2) 写入 RawNews（基于 url unique 防重复）
3) AIAnalyzer 批处理分析标题
4) 写入 SentimentSignal
5) 查询“当日情绪分最高且 risk_tags 为空”的 Top1
6) 初始化 IBExecutor（默认 dry_run=True），执行 $40 定投

关键要求：
- 任何一步失败都要可控：记录错误并安全退出（不交易）
- DRY_RUN 默认 true（除非环境变量显式关闭）
- 记录关键统计：抓取条数、落库条数、AI 成功条数、Top1 结果

## 5) docker-compose.yml（必须实现）
服务：
- postgres（PostgreSQL 15，挂载数据卷）
- ib-gateway（镜像 gnzsnz/ib-gateway-docker）
  - env: TWS_USERID、TWS_PASSWORD（引用 .env）
  - env: TRADING_MODE=paper
  - ports: 4001(API)、5900(VNC)
- app（Python 应用）
  - depends_on: postgres, ib-gateway
  - env: DATABASE_URL, DEEPSEEK_API_KEY, Reddit keys, DRY_RUN
  - command: python -m app.main

## 6) .env.example（必须提供）
包含但不写真实值：
- POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB
- DATABASE_URL=postgresql+asyncpg://...
- DEEPSEEK_API_KEY=
- REDDIT_CLIENT_ID=
- REDDIT_CLIENT_SECRET=
- REDDIT_USER_AGENT=
- TWS_USERID=
- TWS_PASSWORD=
- TRADING_MODE=paper
- DRY_RUN=true

## 7) 最小可运行验收标准（必须做到）
- docker compose up -d 能启动 postgres、ib-gateway、app
- app 启动后能：
  - 抓到 RSS/Reddit 若干条（允许 0 条，但不能报错崩溃）
  - DeepSeek 返回可解析 JSON（若失败要重试并可降级退出）
  - DB 中写入 RawNews 与 SentimentSignal
  - 能选出 Top1（如果没有则安全跳过）
  - dry_run=true 时打印“模拟买入 $40 TICKER”，且不发送订单

## 8) 实施步骤（给 Codex 的任务清单）
按以下顺序实现（不要跳步）：
1) 创建目录结构与骨架文件（空实现 + type hints）
2) 完成 docker-compose.yml + .env.example
3) 完成 DB models + session（Async）
4) 完成 RSSCollector + RedditCollector（去重）
5) 完成 AIAnalyzer（批处理 + JSON 严格解析 + tenacity 重试 + timeout）
6) 完成查询 Top1（risk_tags 为空）逻辑
7) 完成 IBExecutor（AsyncIO + dry_run 安全开关 + 碎股下单）
8) 完成 main.py 串联（异常处理 + 日志）
9) 本地验收：dry_run=true 跑通全流程

## 9) 输出格式与日志规范
- 使用 loguru
- 关键日志必须中文，且包含可排障字段（source、count、ticker、score、risk_tags、price、qty）
- 对外部调用（DeepSeek/IB）失败记录 error；对可恢复问题记录 warning；去重跳过可用 debug

## 10) 禁止事项
- 禁止引入本地 NLP 模型（如 transformers、spacy）
- 禁止默认真实下单
- 禁止在 AI 输出不可信/无法解析时继续交易
- 禁止在没有价格或 qty 异常时下单

完成后请提交所有文件，并确保 `python -m app.main` 在容器内可运行。