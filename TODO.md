# TODO — AI-Quant System (US Sentiment Auto-Invest)

> 目标：先跑通全自动链路，在 **DRY_RUN=true** 下完成端到端验收；再小额、低频、可回滚地验证策略有效性与稳定性。

## 0. 最高优先级原则（不讨论）
- 默认 **DRY_RUN=true**，除非你明确改为 false。
- 任意外部依赖失败（RSS/Reddit/AI/IB）都必须降级：**不交易**、写日志、可恢复。
- AI 输出不可解析/长度不匹配 → **整批跳过**（不写库、不交易）。
- 下单前校验：`price>0`、`qty>0`、`qty合理(>1e-6)`；无价格 → 不交易。

---

## 1) 项目骨架与依赖（P0）
- [ ] 按 agents.md 规定创建目录与骨架文件：
  - [ ] `docker-compose.yml`
  - [ ] `.env.example`
  - [ ] `app/__init__.py`
  - [ ] `app/main.py`
  - [ ] `app/collectors/{__init__.py,rss_collector.py,reddit_collector.py}`
  - [ ] `app/processors/{__init__.py,ai_analyzer.py}`
  - [ ] `app/db/{__init__.py,models.py,session.py}`
  - [ ] `app/broker/{__init__.py,executor.py}`
- [ ] `requirements.txt` / 依赖更新：feedparser、praw、tenacity、loguru、sqlalchemy[asyncio]、asyncpg、ib_insync、openai
- [ ] 基础 lint/测试（可选但建议）：pytest

## 2) Docker Compose（P0）
- [ ] `postgres:15` 数据卷持久化
- [ ] `ib-gateway`：`gnzsnz/ib-gateway-docker`，`TRADING_MODE=paper`，端口 `4001/5900`
- [ ] `app`：依赖 postgres/ib-gateway，启动命令 `python -m app.main`
- [ ] 验收：`docker compose up -d` 三服务启动；app 即使外部失败也不崩

## 3) 数据库层（P0）
- [ ] ORM：RawNews / SentimentSignal（UTC timestamptz、url unique、索引）
- [ ] AsyncEngine + AsyncSession（asyncpg）
- [ ] `init_db()`（create_all）
- [ ] 验收：容器启动能建表；重复运行不报错

## 4) 采集器（P0）
- [ ] RSSCollector（feedparser、去重、统一输出 RawNewsIn）
- [ ] RedditCollector（praw、env keys、去重、失败降级返回空）
- [ ] 验收：无 key/无网络时安全返回空并记录 warning

## 5) AI 分析器（P0）
- [ ] DeepSeek V3 via openai SDK（base_url=https://api.deepseek.com）
- [ ] timeout(20~30s) + tenacity 指数退避最多 4 次
- [ ] 每批 10~20 条标题，要求纯 JSON 数组、长度一致
- [ ] 解析失败整批跳过；强制字段校验与裁剪
- [ ] 验收：失败重试生效；解析失败不落库不交易

## 6) 交易信号（P0）
- [ ] 写入 SentimentSignal（score/risk_tags/ai_summary/created_at UTC）
- [ ] 查询 Top1：当日最高分且 `risk_tags` 为空，ticker 非空
- [ ] 验收：无 Top1 安全跳过；有 Top1 输出日志

## 7) IB 执行器（P0）
- [ ] AsyncIO：connectAsync / reqTickersAsync
- [ ] 碎股：qty = amount_usd / price；MarketOrder BUY
- [ ] dry_run 默认 true：只记录“模拟买入 $40 TICKER”
- [ ] 异常与日志：ticker/amount/price/qty/orderStatus
- [ ] 验收：dry_run 下绝不下单；无价格/qty 异常时不交易

## 8) main 编排与可观测性（P0）
- [ ] 严格顺序：collect → RawNews 入库 → analyze → Signal 入库 → Top1 → buy
- [ ] 关键统计中文日志：抓取条数、落库条数、AI 成功条数、Top1
- [ ] 任一步失败：记录并安全退出（不交易）
- [ ] 验收：dry_run=true 端到端跑通

---

## 9) 策略验证与“先盈利生存”（P1：在系统稳定后）
- [ ] 先做 **观测期**：只记录信号与“如果买了会怎样”（paper/回测）
- [ ] 基线指标：命中率、平均收益、最大回撤、交易次数、胜率与赔率
- [ ] 风控：单日/单票最大投入、冷却时间、黑名单、风险标签过滤
- [ ] 上线节奏：paper → 极小真实资金（若你明确允许）→ 逐步放量

## 10) 交易上线前的明确确认（必须）
- [ ] 你明确下指令：`DRY_RUN=false`（否则永久模拟）
- [ ] 明确资金与频率：默认 `$40/天`、Top1 单票
- [ ] 明确失败处理：AI/IB/价格获取失败当天不交易
