Research App MVP 设计文档（重构版）

1. 概览与目标
   - 单用户 research app，提供 watchlist 维护、定时模型研究、结构化结果展示与最小闭环评估。
   - 不做用户体系、复杂前端、多 agent、自动/纸上交易、复杂回测或调度。

2. 范围与非目标
   - 范围：基础 UI、定时 research、结构化落库、简易 eval、最小部署与运维指引。
   - 非目标：登录/权限、React/SPA/WebSocket、Redis 或复杂队列、宏观/社媒/SEC 深度解析、复杂多模型比较。

3. 系统架构概览
   - FastAPI Web：/watchlist、/research 列表与详情、手动触发入口。
   - Postgres：存储 watchlist、research_runs、research_outputs、eval_results。
   - run_research.py：读取 watchlist，抓取最小数据，调用 LLM，写入输出。
   - eval_runs.py：为过期 run 计算基于有效评估窗口的回测结果并写入 eval。
   - scheduler：定时触发 research 与 eval（串行即可，后续可扩展）。

4. 核心模块说明
   - Web/UI（app.py，templates/*，static/style.css）：展示与表单处理；仅服务器渲染。
   - agent/LLM（run_research.py，llm_client.py，tool/get_market_data.py，tool/get_news_data.py）：分层封装数据源与模型调用；串行处理全部 active tickers；LLM 层使用 Phidata Agent，工具通过依赖注入集中管理上下文与外部连接。
   - Eval（eval_runs.py）：扫描未评估且超过**有效评估窗口**的 run，写 realized_return、benchmark_return、outcome_label 等；有效窗口=research_outputs.time_horizon（1d/3d/5d），若缺失/无效直接报错并标记 run 需人工处理；evaluation_method 可配置。
   - DB 访问（db.py，models.py）：连接管理与基础 CRUD；输入/输出 JSON 全量存储便于回放。
   - Config（config.py）：环境变量、路径（含 Postgres 数据目录）统一管理。

5. Data Model & Tables
   - Table list:

     | table | key fields | notes |
     | --- | --- | --- |
     | watchlists | id uuid pk; ticker text unique; is_active bool default true; created_at timestamptz | tracked tickers |
     | research_runs | run_id uuid pk; ticker text; as_of timestamptz; prompt_version text; model_name text; input_json jsonb; status text default 'queued'; error_message text; started_at timestamptz; finished_at timestamptz; created_at timestamptz | run metadata + input snapshot + 运行状态/错误 |
     | research_outputs | run_id uuid pk fk runs; output_json jsonb; decision text; confidence numeric; time_horizon text; actionability text; thesis_summary text; created_at timestamptz | structured model output |
     | eval_results | run_id uuid pk fk runs; horizon_days int not null; realized_return numeric; benchmark_return numeric; benchmark_symbol text default 'SPY'; evaluation_method text default 'rule_v1'; evaluation_params jsonb 包括eval时抓取的market_data; outcome_label text; created_at timestamptz | eval closure（horizon/method aware；horizon_days=输出的有效评估窗口） |

   - Enumerations:

     | field | allowed values |
     | --- | --- |
     | status | queued, running, succeeded, failed |
     | decision | bullish, bearish, neutral, abstain |
     | confidence | numeric 0–1 |
     | time_horizon | 1d, 3d, 5d |
     | actionability | abstain, watch, actionable |
     | outcome_label | correct, partially_correct, wrong_direction, uninformative |
     | evaluation_method | rule_v1 (default), future methods allowed |

   - Status 语义：run 创建时 status=queued；run_research 启动时写 started_at 并置 running；成功写 outputs 后置 succeeded 且写 finished_at；失败则写 failed、error_message、finished_at。UI 可据此区分“未跑”“运行中”“成功”“失败”。

6. Structured Output JSON Schema (summary)
   - Required: decision, confidence, time_horizon, actionability, thesis_summary, key_drivers[], counterarguments[], invalidators[].
   - Constraints: enums per table above; confidence 0–1; arrays are string arrays.
   - Full schema in Appendix C.

7. Research 输入 schema 与数据源抽象
   - 输入字段：ticker, as_of, price_snapshot{last_price, return_1d, return_5d, return_since_market_open}, context{sector, earnings_in_days，可为 null}, news[title, summary] 3-5 条。
   - 目标：保证可回放同一 case；input_json 存于 research_runs。
   - 数据源接口契约：
     - market_data.get_snapshot(ticker) -> {last_price, return_1d, return_5d, return_since_market_open?, sector?, earnings_in_days?}
     - news_data.get_recent(ticker, limit=5) -> [{title, summary}]
   - 模块可替换；调用层不依赖具体提供商，只依赖接口结果格式。
   - 最小实现建议：
     - collector/market_data.py：使用 yfinance 拉取最新价格与过去 1d/5d 收盘价计算 return；若处于美股常规交易时段，再补充相对当日开盘价的 `return_since_market_open`；可选 sector、earnings 距离从 yfinance 基本信息获取；对缺失字段返回 None。
     - collector/news_data.py：若有 NewsAPI key，优先调用；否则使用 yfinance.Ticker.news 或简单占位返回最近标题与摘要列表；限制 3–5 条；对无新闻返回空列表。
     - 错误处理：数据源失败时记录日志并在 output 中标记无法获取，但不中断其他 ticker；保持接口返回格式。
   - 采集方式：按需拉取、直接落库。run_research 调用 market_data/news_data 获取实时快照后写入 research_runs.input_json；eval_runs 仅在需要回测时调用 market_data 获取价格，news 可选备注；不再做额外预取/缓存或独立采集进程。

8. Prompt 设计与版本管理与 Agent 框架
   - 单一版本 v1，强调谨慎、允许 abstain、基于输入、明确 horizon、提供反方与 invalidators。
   - Prompt 放独立 YAML 文件（如 prompts/research_v1.yaml，包含 id/version/description/body）；升级只需改 version 标识与内容文件。
   - 默认模型：`RESEARCH_MODEL_NAME` 未设置时默认使用 `gemini-2.5-flash-lite`，优先考虑 MVP 成本效率；如需切换其他模型，保持通过环境变量覆盖，不把 provider 细节散落到 orchestration 代码里。
   - Agent 框架（MVP 边界）：采用 hybrid 方案。custom orchestration 负责 watchlist 遍历、market/news/DB 数据获取、`input_json` 快照落库、run 状态流转、错误隔离、结果持久化与 eval；Phidata Agent 仅负责单次 LLM 调用与返回原始响应。
   - MVP 不启用 Phidata 的动态 tool-calling。market_data、news_data、insider 查询等工具由 Python orchestration 在模型调用前直接执行，再把结果整理进 prompt/input snapshot；这样可保证 replayability、可测试性与稳定的 eval 输入。
   - 每个 ticker/run 建立独立上下文，避免跨标的泄漏；上下文控制（history truncation / selective recall）继续由 orchestration/tool 层决定。`show_tool_calls` 仅保留给未来引入动态 tool-calling 时的调试场景，不作为 MVP 运行路径的依赖。
   - 详细边界与取舍见 `plan/research_app/architecture_recommendation.md`。

9. 运行流程
   - research cron：读取所有 active tickers -> 在 Python orchestration 中现场拉取 market snapshot + news + 必要 DB context -> 写入 `research_runs.input_json` 快照 -> 调用 Phidata 包装的单次 LLM -> 直接写 runs/outputs 入 Postgres；频率建议工作日盘前或每日 1-2 次。插入 run 时 status=queued，开始处理某 ticker 时置 running+started_at，成功后置 succeeded+finished_at，失败则置 failed 并写 error_message+finished_at（不中断其他 ticker）。
   - eval cron：仅处理具备有效 time_horizon 的 run -> 通过 market_data 按需获取 realized/benchmark return -> 按 evaluation_method 计算 outcome_label -> 写 eval_results；若缺失/无效 time_horizon 则记录错误并跳过；频率每日一次夜间。
   - 采集复用：两条 cron 都调用同一 market_data/news_data 抽象，按需请求，无额外缓存/中间存储。MVP 中 LLM 不直接调用外部 tools。
   - 手动触发：POST /admin/run-now 或等效脚本，仅限本机/内网，便于调试。

10. UI 与路由
   - GET /watchlist：表格列 ticker、状态；输入框添加；行级删除或停用。
   - POST /watchlist/add；POST /watchlist/{id}/delete 或 /watchlist/delete。
   - GET /research：表格列 ticker、分析时间、decision、confidence、actionability、time_horizon、thesis_summary；顶部展示聚合 eval 结果（可按 outcome_label、horizon_days、evaluation_method 汇总；最近 N 天正确率）。
   - GET /research/{run_id}：展示 input_json、output_json、eval outcome_label（可用 <pre>）；可附上该 ticker 的历史 eval 小结。

11. 部署与运维要点
   - 单机部署，Postgres 数据目录固定在持久化磁盘（非 tmpfs）；树莓派需确认磁盘挂载。
   - scheduler 采用系统 cron 或等效方案；成本与频率记录在 runbook。
   - 详细步骤见 documents/research_app_deploy.md；运维常见操作见 documents/research_app_runbook.md。

12. 验收标准
   1. /watchlist 可添加 ticker，刷新可见。
   2. 手动运行 run_research.py 产生新的 research_runs 与 research_outputs。
   3. /research 列表显示新增结果，详情页可见输入/输出 JSON。
   4. 手动运行 eval_runs.py 后，详情页可见 outcome_label。
   5. Postgres 数据目录确认在硬盘路径，不在临时目录。
   6. 树莓派重启后数据仍存在。

13. 实现顺序
   1. 建表与最小 FastAPI UI（watchlist 增删）。
   2. run_research.py + 最小 collector，生成一条假或真输出并落库。
   3. 接入真实 market_data/news_data 与 LLM 结构化输出。
   4. 完成 /research 列表与详情页。
   5. 实现 eval_runs.py 与定时任务。
   6. 编写部署文档与持久化验证收尾。
  
14. 演进规划 (Future Work)
本项目的核心理念为“先构建最小可用闭环，再逐步演进”。在 MVP 阶段跑通数据流与 Rule-based 评估后，系统将向“具备自我反思能力”和“多技能协同”的复杂 Agent 架构演进。以下为核心演进方向与架构预留：

  1. Critic（反思/批评）机制与自我进化
  当前系统的 eval_runs.py 提供客观的量化评估（Outcome Label），未来将引入 Critic Agent 进行主观归因与知识沉淀，实现系统的“自我进化”。
    - 数据库模型扩展：扩展 eval_results 表或新增 reflections 表，用于存储 Critic Agent 的结构化反思结果。
    - 核心字段预留： error_reason (错误归因), lesson_learned (经验教训)。
    - 触发与执行流 (Workflow)：
      当定时任务 eval_runs.py 计算出 outcome_label 为 wrong_direction 且置信度 (confidence) 较高时，异步触发 Critic Agent。
    - 输入上下文： 历史的 input_json (当时看到的数据)、output_json (当时的判断)、以及包含期间真实走势与回撤的 market_data。
    - 核心校验逻辑： 
      Critic 将重点比对预设的 invalidators（证伪条件）。若亏损但触及 invalidators，说明逻辑合理但宏观/基本面生 变；若未触及 invalidators 却出现方向性错误，则提取 lesson_learned。
    - 进化闭环 (Context Injection)：
      当下一次 Research Agent 对同一标的或同板块发起分析时，系统将从 DB 中检索相关的 lesson_learned，作为动态 Context 注入到 Prompt 中（例如：“注意防范过往在类似技术面破位时的误判”），从而干预并优化下一次的决策生成。

  2. 工具注册表 (Tool Registry) 与多技能 (Skills) 路由架构
  随着分析维度增加，将告别单一的巨型 Agent，转向“工具按需加载”与“多专家协同”的灵活架构，以降低 Token 消耗并减少模型幻觉。
    - Tool Registry 解耦模式：
      MVP 阶段先保持 orchestration 直连工具并在模型调用前完成数据采集；未来若需要动态 tool selection，再建立工具注册表机制。届时将外部数据源（如 SEC Filings, GitHub 趋势, 宏观经济指标）封装为独立的纯 Python 函数工具，并在补齐 tool-call audit log / replay 规则后，再按 input_json 上下文动态组装并挂载 Tools 列表给 Agent。
    - Skills 机制与 Router 节点：
    Skill 定义： 
      将不同场景的分析逻辑抽象为独立的 Sub-Agents（Skills），例如 Macro_Skill（关注利率与宏观数据）、Earnings_Skill（关注财报突发事件）或 Momentum_Skill（纯技术面动量突破）。
    路由分发 (Router)： 
      在 run_research.py 前置一个轻量级 Router（基于 Rule-based 规则或极小的 LLM 调用）。Router 根据当前标的的市场环境特征，决定激活哪一个（或组合哪几个）Skill Agent 来执行特定的 Research 任务，并将最终结果汇总落库。
  
  3. More tools
   - market news tools from Finnhub 

15. 附录
   - A. 工具注入与 Agent 示例（沿用现有片段）：
     ```
     from phi.agent import Agent
     from phi.model.openai import OpenAIChat
     # 依赖注入示例（保持原文）
     class RecommendationTools:
         def __init__(self, feature_store_client, retrieval_client):
             self.fs_client = feature_store_client
             self.retrieval_client = retrieval_client
         def get_user_features(self, user_id: str) -> str:
             features = self.fs_client.get(f"user_features:{user_id}")
             return f\"User {user_id} features: {features}\"
         def get_restaurant_embedding(self, restaurant_id: str) -> str:
             embedding = self.retrieval_client.fetch(restaurant_id)
             return f\"Restaurant {restaurant_id} embedding loaded.\"
     global_fs_client = MockFeatureStorePool()
     global_retrieval_client = MockRetrievalClient()
     recsys_tools = RecommendationTools(global_fs_client, global_retrieval_client)
     agent = Agent(
         model=OpenAIChat(id=\"gpt-4o\"),
         tools=[recsys_tools.get_user_features, recsys_tools.get_restaurant_embedding],
         show_tool_calls=True,
     )
     agent.print_response(\"帮我查一下 user_123 的特征，以及 restaurant_456 的 embedding。\")
     ```
   - B. SQL schema (reference):
     ```
     create table if not exists watchlists (
       id uuid primary key,
       ticker text not null unique,
       is_active boolean not null default true,
       created_at timestamptz not null default now()
     );

     create table if not exists research_runs (
       run_id uuid primary key,
       ticker text not null,
       as_of timestamptz not null,
       prompt_version text not null,
       model_name text not null,
       input_json jsonb not null,
       status text not null default 'queued',
       error_message text,
       started_at timestamptz,
       finished_at timestamptz,
       created_at timestamptz not null default now()
     );

     create table if not exists research_outputs (
       run_id uuid primary key references research_runs(run_id),
       output_json jsonb not null,
       decision text not null,
       confidence numeric not null,
       time_horizon text not null,
       actionability text not null,
       thesis_summary text not null,
       created_at timestamptz not null default now()
     );

     create table if not exists eval_results (
       run_id uuid primary key references research_runs(run_id),
       horizon_days int not null default 3,
       realized_return numeric,
       benchmark_return numeric,
       benchmark_symbol text not null default 'SPY',
       evaluation_method text not null default 'rule_v1',
       evaluation_params jsonb,
       outcome_label text,
       created_at timestamptz not null default now()
     );
     ```
   - C. Structured Output JSON schema:
     ```
     {
       "type": "object",
       "additionalProperties": false,
       "properties": {
         "decision": { "type": "string", "enum": ["bullish", "bearish", "neutral", "abstain"] },
         "confidence": { "type": "number", "minimum": 0, "maximum": 1 },
         "time_horizon": { "type": "string", "enum": ["1d", "3d", "5d"] },
         "actionability": { "type": "string", "enum": ["abstain", "watch", "actionable"] },
         "thesis_summary": { "type": "string" },
         "key_drivers": { "type": "array", "items": { "type": "string" } },
         "counterarguments": { "type": "array", "items": { "type": "string" } },
         "invalidators": { "type": "array", "items": { "type": "string" } }
       },
       "required": [
         "decision", "confidence", "time_horizon", "actionability",
         "thesis_summary", "key_drivers", "counterarguments", "invalidators"
       ]
     }
     ```
