# Plan — AI-Quant System (US Sentiment Auto-Invest)

## 1. 项目目标（阶段化）

### 阶段 A：系统跑通（稳定性优先）
- 在低功耗 Linux 服务器上，基于 Docker Compose 跑通：采集 → AI 分析 → 入库 → 选 Top1 → IB 执行（dry-run）。
- 任何外部依赖失败都不导致崩溃；失败时不交易。

### 阶段 B：策略验证（先“生存”）
- 先 paper/模拟观测：持续记录信号与后续表现，建立统计置信度。
- 在你明确授权后，才进入小额真实交易。

> 关键：策略正确性验证要靠数据与统计，而不是一次两次的运气。

---

## 2. 核心约束（来自 agents.md）
- Python 3.10+，所有 public 函数必须 type hints。
- DeepSeek V3（openai SDK，OpenAI 兼容格式）。
- IBKR via ib_insync（必须 AsyncIO）。
- PostgreSQL 15（Docker）+ SQLAlchemy ORM（建议 Async + asyncpg）。
- 关键库：feedparser、praw、tenacity、loguru。

---

## 3. 系统架构（数据流）
1) Collectors
- RSS：Yahoo Finance、CNBC 等 RSS，输出 RawNewsIn
- Reddit：r/stocks、r/investing，输出 RawNewsIn

2) DB
- RawNews：原始标题、来源、url、抓取时间（UTC），url 唯一
- SentimentSignal：ticker/score/risk_tags/summary/created_at（UTC）

3) AI
- 批处理标题 → DeepSeek 输出严格 JSON 数组 → 校验与裁剪

4) Signal
- Top1：当日最高分，且 risk_tags 为空（无风险标签）

5) Broker
- IBExecutor：dry_run 默认 true；否则按金额碎股市价买入

---

## 4. 风险控制与上线门槛

### 4.1 交易安全（强制）
- `DRY_RUN=true` 为默认；除非你明确设置 `false`。
- 下单前校验：price>0、qty>0、qty>1e-6。
- 获取不到价格或异常 → 当天不交易。

### 4.2 AI 输出安全（强制）
- 必须是纯 JSON；解析失败或长度不匹配 → 整批丢弃。
- sentiment 裁剪到 [-1,1]。
- ticker 不明确必须为 null（禁止猜测）。

### 4.3 稳定性
- DeepSeek client timeout（建议 25s）。
- tenacity 指数退避最多 4 次。
- 任何外部依赖失败：降级继续（但不交易）。

---

## 5. 验收标准（最小可运行）
- `docker compose up -d` 启动 postgres、ib-gateway、app。
- app：
  - 能抓 RSS/Reddit（允许 0 条，不崩）。
  - DeepSeek 可解析 JSON（失败重试，仍失败则安全退出不交易）。
  - DB 写入 RawNews 与 SentimentSignal。
  - 选出 Top1（无则跳过）。
  - dry_run=true 时打印“模拟买入 $40 TICKER”，不下单。

---

## 6. 实施节奏建议（避免一口吃胖）
1) 先把 DB + collectors 跑通（不接 AI/IB）
2) 接 AIAnalyzer（只写库，不交易）
3) 接 Top1 查询
4) 接 IBExecutor（dry_run）
5) 稳定跑一周：看数据质量与信号分布
6) 再讨论策略改进与是否小额实盘

---

## 7. 下一步我会做什么（等你确认）
- 直接开始按 TODO.md 的 P0 顺序开发：先创建 `app/` 目录骨架 + docker-compose + .env.example。
- 完成后每一步都提交一次（小步提交，方便回滚）。

你确认我现在就开始动手开发吗？（默认保持 dry_run=true）
