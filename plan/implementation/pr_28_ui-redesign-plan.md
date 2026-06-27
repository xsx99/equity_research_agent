# Trading App UI 重做 — 实现说明（P0–P4 已完成）

> 本文是**可照抄的实现 instruction**：按阶段列出改了哪些文件、函数、字段、模板块、CSS、测试。
> 架构：`src/templates/today.html`（单页多 tab，Jinja 服务端渲染）+ `src/web/presenters/*` + `src/web/routers/today.py`。
> 验证约定：仅做代码改动，`pytest` / 渲染验证由人来跑（本机无 fastapi/jinja2）。
> 自检手段：`python3 -m py_compile <file>`；模板用正则数 `{% if/for/block %}` 与对应 `end*` 是否配平。

Tab 事实：`_TAB_LABELS`（`today.py:76`）= Portfolio / Trades / Candidates / Risk & Macro / System。**没有 Overview tab**；模板里的 `{% elif selected_tab == "overview" %}` 是死分支。顶部常驻 KPI 头（`today.html` header）在所有 tab 显示。

---

## P0 — 低成本快赢

### #9 展示 trade weight（`approved_weight`，来自 decision 链路）
- `today_workspace.py` `_build_detail`：`latest_conclusion.trade_decision` 字典加 `"approved_weight": latest_decision.get("approved_weight")`。
- `today_workspace.py` `_history_trade_decision_view`：返回值加 `"approved_weight": row.get("approved_weight")`。
- `today.html`：
  - Trades detail hero 的 `hero-meta-pills` 里，在 Confidence pill 后加 Weight pill：
    `{% if detail.latest_conclusion.trade_decision.approved_weight is not none %}<span class="meta-pill">…{{ "%.1f%%"|format(... * 100) }}</span>{% endif %}`
  - History timeline 卡片 Trade Decision 行的 `<strong>` 追加 ` · {{ "%.1f%%"|format(trade_decision.approved_weight * 100) }}`（带 `is defined and is not none` 守卫）。
- 数据已存在：`today.py:_serialize_trade_row` 已序列化 `approved_weight`（`TradingDecision.approved_weight`，0–1 小数 Decimal）。

### #1 "Needs Review" 改名
- `today.html`：Overview/Portfolio 三处 `Needs Review` →
  - summary tile → `Ready for Review`
  - section 标题 → `Recently Closed · Ready for Review`，Overview 那处加副标题 `<p class="detail-muted">Positions closed recently and awaiting post-trade review.</p>`
- 语义来源：`today_overview.py:_build_command_center` 的 `needs_review` = 最近平仓待复盘。

### #3 Trades 新闻摘要截断（之前显示整篇正文）
- `today_workspace.py`：新增 `_truncate_news_text(value, *, limit=280)`：归一空白；≤limit 原样返回；否则优先句子边界（`". "/"! "/"? "`，需 ≥limit//2）截断，否则词边界，末尾补 `…`。常量 `_NEWS_SUMMARY_MAX_CHARS = 280`。
- `_build_event_news_summary`：`summary = _truncate_news_text(str(primary_snippet.get("summary") or "").strip())`。

---

## P1 — Trade Plan / Bull-Bear / Agent 面板 / 信号共享函数

### #4 抽共享信号渲染（candidates 与 trades 复用）
- 新建 `src/web/presenters/signal_evidence.py`：
  - `signal_bullets(evidence) -> tuple[str]`：**与原 candidates `_signal_bullets` 输出逐字一致**（News+Insider 合并在 "News:"）。保 `tests/web/test_today_candidates.py` 断言不破。key 列表 `_TECHNICAL_KEYS / _FUNDAMENTAL_KEYS / _NEWS_KEYS(events_news+news) / _INSIDER_KEYS`，flat 版用 `_NEWS_KEYS + _INSIDER_KEYS`。
  - `signal_groups(evidence) -> tuple[dict]`：**新结构化输出**，按 Technical / Fundamental / News & Events / Insider 分开成 `{"key","label","bullets"}`（Insider 独立）。
  - 公共 helper：`clean_copy` / `clean_fragment`，私有 `_signal_group_parts / _signal_part / _flatten_evidence / _as_float`（从 candidates 整体搬过来）。导入 `operator_text` 自 `today_copy`。
- `today_candidates.py`：删除上述被搬走的私有函数；`from src.web.presenters.signal_evidence import clean_copy, clean_fragment, signal_bullets`；调用点 `_clean_copy→clean_copy`、`_signal_bullets→signal_bullets`；保留 `_labeled_bullets` 但改用 `clean_fragment`。

### #8 Trades detail 富化
- `today.py:_serialize_trade_row` 增序列化（`TradingDecision` 列见 `db/models/trading.py:1755`）：
  `target_weight`、`time_horizon`、`max_loss_pct`、`entry_plan`/`exit_plan`（取 `metadata_json`，DB 无专列）、`core_signal_evidence`（取 `row.candidate_score.core_signal_evidence_json`，可能 None → `{}`）。
- `today_workspace.py`：`from .signal_evidence import signal_groups`；`_build_detail` 的 `latest_conclusion` 增三块：
  - `trade_plan`：thesis / time_horizon(humanize) / target_weight / approved_weight / max_loss_pct / entry_plan / exit_plan / `edge`(=key_drivers) / invalidators
  - `bull_bear`：confidence / `bull_points`(=key_drivers) / `bear_points`(=counterarguments) —— **零新数据合成**
  - `signal_groups`：`signal_groups(latest_decision.get("core_signal_evidence"))`
- `today.html` Trades detail（在 `ticker-support-grid` 之后、`ticker-detail-nav` 之前）新增：
  - `data-testid="trade-plan"`：Thesis + weight/maxloss/horizon pills + Edge/Entry/Exit/Invalidation 列表（各字段 `{% if %}` 守卫）
  - `data-testid="bull-bear"`：两栏 Bull Case / Bear Case（用 `ticker-support-grid` 容器），conviction chip
  - `data-testid="signal-groups"`：用 `signal-summary-grid`/`signal-summary-card` 渲染 `signal_groups` 每个 section
- History timeline：`_history_trade_decision_view` 加 `"thesis"`；卡片 Trade Decision 段渲染 `{% if trade_decision.thesis is defined and trade_decision.thesis %}…`

---

## P2 — Tab 重分工 / Attention Feed / Watchlist 归 Candidates

### 决策1 Overview/Portfolio + (2a) 头部
- Overview 是死分支，不动。"概览"由常驻 KPI 头承担。
- `today.html` header KPI 区：在 Unrealized P&L 后加 **Realized P&L** tile（`header.realized_pnl`，已由 `_build_header` 提供，`today.py:448`），带 `kpi-pos/kpi-neg` 着色。

### (2b) Portfolio Attention Feed 合并
- `today.html` Portfolio "Needs Attention" 区：删掉三列 `needs-attention-grid`，换成单列 `<ul class="attention-feed">`：
  依次 `live_alerts`(`Alert` 徽章) → `material_changes`(`Signal Change`) → `needs_review`(`Review`)，每行 ticker 链接 + 文案。空态保留 "Nothing needs attention"。
- `style.css` 新增 `.attention-feed` / `.attention-feed-row` / `.attention-badge` + `.attention-badge-alert/-signal/-review`。

### 决策2 Watchlist 归 Candidates + 评估 timeline
- `today.html` Trades 侧栏：rail 循环与外层渲染条件移除 `watch` bucket（保留 action_now/open_positions/closed_today/reviewing）。
- `today_workspace.py`：`_default_selected_ticker` 顺序**保留** `watch`（否则破 `test_build_ticker_workspace_defaults_to_first_watch_ticker`）；外层模板条件已排除 watch，watch-only 状态走空态，无矛盾。bucket 仍照常构建（多个 `buckets["watch"]` 测试依赖）。
- `today_candidates.py`：`_group_candidate_rows` 每个 group 加 `evaluations`——按 `decision_time` 倒序的 `{decision_time, outcome, strategy_label, confidence, summary}` 列表（复用已分组 `sorted_items`，零新查询）。
- `today.html` Candidates 决策卡：在 Signals Used 后、alternatives 前，加 `{% if row.evaluations and row.evaluations|length > 1 %}` 的 `<details>` Evaluation timeline（`<ol class="candidate-timeline-list">`）。

### P2 测试同步（`tests/web/test_today.py`）
- Trades：`assert "Watch" in response.text` → `assert 'data-bucket="watch"' not in response.text`
- Portfolio：`Needs Review/Live Alerts/Material Changes` 断言 → `Needs Attention` + `attention-feed` + `Signal Change`
- `test_get_today_dashboard_renders_portfolio_home_header_and_tabs`：`"Needs Review"` → `"Needs Attention"`

---

## P3 — Risk 页 Catalyst Calendar（#6a）

- `today.html` risk-macro tab 的 "Event Risk" 段改为双栏：用 Jinja `namespace` 按 `'earnings' in (row.event_type|string|lower)` 把 `risk_macro.events` 拆成 `ns.earn` / `ns.econ`（**模板侧拆**，因集成测试直接喂 `events` dict）。
  - `data-testid="economic-calendar"`：`<ul class="calendar-list">` 行 = 日期 + 标题 + `impact-{high/medium/low}` 徽章（`importance|upper`）
  - `data-testid="upcoming-earnings"`：`earnings-card-list` → `earnings-chip`（ticker + 徽章 + 日期 + risk_mechanism）
- `style.css` 新增 `.risk-calendar-grid` / `.calendar-list` / `.calendar-row` / `.impact-badge`(+high/medium/low) / `.earnings-card-list` / `.earnings-chip` / `.earnings-chip-head`。
- 测试 `test_risk_macro_tab_renders_summary_first_structure`：`event-risk-list` / `"AAPL / high"` → `economic-calendar` + `upcoming-earnings` + `"AAPL"` + `"HIGH"`（`"direct earnings gap risk"` 保留）。
- 数据：Economic Calendar 用现成 `CalendarEvent`（`today_risk_macro.py:_event_row`）。Earnings 仅日期+ticker+影响等级（EPS/AM-PM/veto 见 Future Work）。

---

## P4 — Portfolio Equity 时序图 + 日级指标（#7，需后端）

- 新建 `src/web/presenters/today_portfolio_analytics.py`：纯函数 `build_portfolio_analytics(history, *, width=720, height=180)`。
  - 入参 `history` 旧→新，每项 `{time, equity, day_pnl}`；无 equity 数据返回 `None`。
  - 输出 inline-SVG 几何：`equity_points`（polyline 坐标串）、`daily_bars`（零基线柱 `{x,y,w,h,positive}`、`baseline_y`）、`equity_start/end/min/max`、`point_count`。
  - `metrics`（**账户/日级，非逐笔**）：`total_return`、`max_drawdown`(equity 峰谷)、`win_days`/`loss_days`、`profitable_days_pct`、`best_day`/`worst_day`、`avg_day_pnl`、`daily_profit_factor`(gross win/gross loss of day_pnl)。
- `today.py`：新增 `_load_portfolio_history(session, *, limit=180)`（`PortfolioSnapshot` desc 取后 reversed→升序，`{time,equity,day_pnl}`）；`import build_portfolio_analytics`；`_build_portfolio_view` 加形参 `portfolio_history=None` 并返回 `"analytics": build_portfolio_analytics(portfolio_history or [])`；调用点传 `portfolio_history=_load_portfolio_history(session)`。
- `today.html` Portfolio 顶部 `{% if portfolio.analytics %}`：Portfolio Value Over Time（`<svg><polyline class="equity-line">`）+ Daily P&L（`<svg>` baseline + 每柱 `<rect class="pnl-bar-pos/-neg">`）+ `overview-metric-grid` 6 张指标卡（Total Return / Realized P&L / Max Drawdown / Profitable Days / Avg Daily P&L / Best-Worst Day）。`data-testid="portfolio-analytics"`。
- `style.css` 新增 `.portfolio-charts` / `.portfolio-chart-card` / `.equity-chart` / `.pnl-chart` / `.equity-line` / `.pnl-baseline` / `.pnl-bar-pos` / `.pnl-bar-neg` / `.chart-axis`。
- 新增 `tests/web/test_today_portfolio_analytics.py`（纯函数单测：空/单点边界、series 长度、total_return/max_drawdown/win-loss/best-worst/daily_profit_factor）。
- 守卫：fixture 无 `analytics` → 块隐藏，旧 Portfolio 测试不破。

---

## Future Work（与本次 UI 解耦的后续独立项）

1. **Trade-outcome ledger（解锁逐笔指标）**
   现状：DB 无可查询的逐笔平仓 P&L（`PaperPosition` 无 realized_pnl 列，仅 `PortfolioSnapshot` 累计 realized + 每快照 day_pnl）。
   待办：落一张逐笔平仓结果表（或由 `PaperExecution` 成交配对买卖计算每笔 P&L）。有了它才能把 P4 的"日级"指标升级为 Image #7 的**逐笔** Win Rate（W/L 计数）、Profit Factor、Expectancy、Best/Worst Closed Trade，并在 Portfolio 指标卡替换/补充。

2. **#6b Upcoming Earnings 数据增强**
   现状：Risk 页 Earnings 卡只有日期 + ticker + 影响等级。
   待办：扩展已在调用 Finnhub `/calendar/earnings` 的 market-data provider，持久化 EPS 估计 + bmo/amc 时段；新增 D0/D+1 与 buy-veto window 逻辑（全新，当前代码无 veto/gate 概念），再在 `today_risk_macro.py:_event_row` 暴露字段、模板 earnings-chip 展示 EPS/AM-PM/GATE 徽章。

3. **图表时间范围切换**
   现状：`_load_portfolio_history` 固定取最近 180 个快照。
   待办：加 7D/30D/90D/6M/1Y/ALL 切换（query param + 限制窗口），前端切换按钮。inline-SVG 方案可直接按窗口重算几何，无需图表库。
