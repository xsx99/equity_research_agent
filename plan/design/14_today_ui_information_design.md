# Design Module 14: `/today` UI 信息呈现（对 D09 的偏差诊断 + 补充原则）

> **与 D09 的关系**：[D09 `09_ui_error_testing_delivery.md`](09_ui_error_testing_delivery.md) 的 "13. UI Design" 已经设计了 `/today` 的导航、状态头、各 tab 和 **Trades 详情的完整 audit trail**（signal snapshot → candidate scores → selected strategy → confidence basis → exit plan/invalidators → post-close outcome）。本文不另起炉灶，而是：(1) 诊断 **as-built 实现对 D09 的偏差**（最大的偏差就是 D09 设计的"审计链"被拆成了互不关联的平行卡、还重复渲染）；(2) 把 D09 没展开的**信息呈现原则**（claim↔evidence 绑定、数据可追问、新鲜度等）写成可执行规则。换句话说：**我的 IP-2 论点↔证据，本质是把 D09 早就要求的 audit trail 真正落地。**
>
> 这份 guide 的重点是**信息怎么呈现**（content / information design）——不是配色，而是「读者打开一个视图，能不能快速看懂决策、依据、和风险」。视觉系统（token / 配色）放在后半部分，作为从属。
>
> 架构：server-rendered，Jinja 模板 `src/templates/`，唯一样式表 `src/static/style.css`，数据由 `src/web/presenters/*` 整形，格式化 helper 在 `src/web/filters.py`。无 JS 框架、无组件库。
>
> 验证约定（memory）：本机无 app 运行环境，只做代码改动 + 写计划；**改完不要凭读代码就宣称完成**，渲染验证交给人/截图。结构性改动按交接计划分批做，不要一次性大改 + push。

---

## 0. 两个已定方向

1. **Overview tab 接回导航**：把 `overview` 加进 `_TAB_LABELS`（`today.py`），让 `today.html:69` 的分支真正可达，`_tab_overview.html` 复活为正式 tab。
2. **视觉统一到扁平灰蓝**（旧 `research.html`/`watchlist.html`/`base.html` 那套）：Today 的暖金渐变、重阴影、超大圆角逐步退役，向扁平灰蓝收敛。详见 §5。

> 这两件是视觉/导航层。下面 §1–§4 才是这份 guide 的核心——信息呈现。

---

## 0.5 渲染验证（本次用真实渲染看出来的问题）

> 虽然本机没装 fastapi，但用 `jinja2` + 测试 fixture（`tests/web/test_today.py:_dashboard_payload`）可以**直接渲染模板**，再用 headless Chrome 截图。复现 recipe：建临时 venv 装 `jinja2`，import fixture（stub 掉 `pytest`/`fastapi` 模块），用带 `__path__` 的 stub 包绕开 `src/web/__init__.py` 的 fastapi import，`filters.register(SimpleNamespace(env=env))` 注册过滤器，渲染后 headless Chrome 截图。（完整 recipe 见 `no-app-env-access` memory；本次的 harness 脚本是临时 scratchpad 文件，非仓库内长存。）**以后改 UI 应该这样自验，而不是只读代码。**

真渲染（5 个 tab + 注入 analytics 的图表）后确认到、光读模板看不出来的问题：

| 类别 | 发现 | 位置（渲染确认） |
|---|---|---|
| 机器值泄漏 | **原始 slug 当 label 显示**，跨 3 个 tab：`macro_high_overlay` / `own_event` / `event_window_check` / `single_name_limit`（Trades 的 Risk Manager 卡）、`risk_config_resolver_v1`（Risk Config Version）、`earnings_drift_v1` / `semis_readthrough_v1` / `market_bars`（System 策略/provider） | trades / risk-macro / system |
| 机器值泄漏 | **百分比强制带 `+` 号**：Net/Gross Exp. 显示 `+31.00% / +42.00%`，Margin Util 同理——`pct()` 永远加正负号，对"盈亏"对、对"敞口/保证金占用"这种非盈亏量是**误导**（敞口不是"涨了 31%"） | KPI 头（所有 tab） |
| 信息层级 | **两个 eyebrow label 叠着**：hero 里 "TRADE DECISION" 正上方又一行 "LATEST CONCLUSION"，一个东西两个标签（IP-1/IP-8） | trades hero |
| 量级缺失 | **confidence 是裸数字 `0.72`**，无条形/无直觉量级（IP-4/IP-5） | trades hero |
| 图表 | analytics 存在时 equity 折线 + P&L 柱**能正常渲染、分两个 panel、不重叠**（好）；但**没有 Y 轴刻度/数值标注**——只看得到形状看不到量级，也无 hover（IP-4/IP-5/IP-7） | portfolio（注入 analytics 后） |
| 图表（好消息） | **退化数据安全**：全平/全 0 序列不崩、不除以 0；但平线贴在 panel 顶边、全 0 的 P&L panel 在标题下渲染成空白（轻微空态问题） | portfolio（flat 序列） |
| 空区块 | fixture 无 `portfolio.analytics` 时，整个图表区块**直接消失**（`{% if %}` 守卫），页面不报错但也没有任何"暂无数据"提示 | portfolio（默认 fixture） |

> 注：`datetime_seconds` / `month_day` 这类 token 来自 `base.html` 的 JS formatter 选项，不是可见文本泄漏，已排除。

---

## 1. 核心理念：视图是「帮人做判断」，不是「数据的容器」

每个视图要按读者脑子里的**问题顺序**组织内容。Trade 视图的问题链应该是：

1. **决策是什么？**（Decision：long/short/hold/trim，方向 + 仓位）
2. **为什么？**（Thesis / rationale，一句话主旨）
3. **每个论点靠什么 evidence 支撑？**（claim ↔ evidence，**最关键**）
4. **什么会推翻它？**（Invalidators，最好带"是否已触发"）
5. **怎么执行、风险多大？**（Plan：sizing、entry/exit、max loss、risk 状态）
6. **它怎么演变到今天？**（Timeline：what changed，而非快照堆叠）

**当前最大问题**：现在的 Trades detail 把这些拆成 5–6 张**平行、互不关联**的卡片（Trade Decision hero / Signal Summary / Trade Plan / Bull-Bear / Signal Groups / History），读者得自己在脑子里把"论点"和"证据"对起来。信息是**铺开的**，不是**组织好的**。

---

## 2. 信息呈现 Principles（每条带现状违例）

### IP-1 — 倒金字塔：结论先行，细节按需展开

读者扫一眼就该拿到结论（决策 + 信心 + 仓位 + 风险状态）；理由、证据、计划、历史**逐层展开**（次级区块 / `<details>`），不要一上来全摊开等量齐观。

**现状**：hero 里 "Trade Decision" 和 "Latest Conclusion" 两个 section-label 叠在一起（`_tab_trades.html:96-97`），label 冗余；而真正的层级（结论→理由→证据）没有体现，全是同级卡片。

---

### IP-2 — 论点绑定证据（claim ↔ evidence）★ 本次最重要

**Why**：一个论点（"营收加速增长"）没有挂着支撑它的数据（"营收增速 0.42 / 20日涨幅 +5.2%"），读者就无法判断这个论点可不可信。把论点放一张卡、证据放另一张卡，等于让读者做连线题。

**现状违例**（确认）：
- `bull_points` / `bear_points`（论点）在 Bull-Bear 卡（`_tab_trades.html:280-321`）。
- `signal_groups`（证据，如 "20d return +5.2%"、"RS vs SPY 3%"）在**另一张** Signal Groups 卡（`:323-355`）。
- `invalidators` 在**第三张** Trade Plan 卡（`:268-275`）。
- 三者之间**零关联**——数据层 `key_drivers` / `counterarguments` / `signal_groups` 就是三个独立的扁平 list（`today_workspace_detail.py:85-135`）。

**目标结构**（论点为主轴，证据内联挂在论点下）：

```
RATIONALE
 ▸ [BULL] Accelerating revenue growth                 conviction ▮▮▮▮▯
     ├ Fundamental · revenue growth 0.42      (as of 06-24 · FMP)
     └ Technical   · 20d return +5.2%         (as of 06-25)
 ▸ [BEAR] Stretched valuation
     └ Fundamental · valuation pctile 0.88    (as of 06-24)

INVALIDATORS
 ▸ Close below 50DMA               ○ not tripped
 ▸ Revenue guide cut next print    ○ not tripped
```

**规则**：每个 claim 内联显示支撑它的 evidence（值 + 方向 + 来源 + 时间）；没有证据的 claim 明确标"no evidence linked"，不要假装。

**落地说明（诚实标注成本）**：
- 这条**需要数据改动**，不是纯模板：现在 `key_drivers` 是裸字符串、与 `signal_groups` 的信号无引用关系。要在 decision 链路上建立 claim → 支撑信号 的关联（每个 driver 带它引用的 signal key 列表），presenter 再据此组装 `rationale: [{claim, direction, conviction, evidence:[{label,value,source,as_of}]}]`。
- 在数据未就绪前，**过渡方案**（纯模板可做）：把 Bull-Bear 与 Signal Groups 两张卡合并为一张"Rationale & Evidence"，论点在上、按 Technical/Fundamental/News 分组的证据在下同卡呈现，至少视觉上聚拢，减少跨卡连线。

---

### IP-3 — 一个事实只出现一次

**现状违例**（确认）：`trade_plan.edge` 与 `bull_bear.bull_points` **是同一份 `tuple(key_drivers)`**（`today_workspace_detail.py:127` vs `:132`），在 Trade Plan 卡和 Bull-Bear 卡里**各渲染一遍**。读者看到两处一样的 bullet，会以为是两组不同信息。

**规则**：同一内容只在一处呈现。Trade Plan 的 "Edge" 段应删除（与 Bull Points 重复），或 Edge 改为真正不同于 key_drivers 的内容。presenter 层去掉重复别名。

---

### IP-4 — 数据要可追问，不只是被展示（hover / drill-down）

数字和图表应该能**回答"具体是多少 / 哪一天"**，而不是只摆一个静态形状。

**应用**：
- **PnL 折线图**：每天的点 hover 时出 tooltip（日期 + equity + 当日 P&L + %）+ 竖线 crosshair。详见 §4。
- **Confidence / weight**：除了数字，配一个进度条（`▮▮▮▮▯`）给出直觉量级。
- **长 list / 表**：默认收起，`<details>` 展开；timeline 默认显示"what changed"，原始快照按需展开。

**现状**：PnL 是静态 polyline + 柱，无 hover；confidence 只有裸数字 `0.62`（`_tab_trades.html:107`）。

---

### IP-5 — 给量级和方向，不只给标签

**规则**：
- 所有盈亏/涨跌**着色** pos/neg 并带符号（KPI 头已做，evidence 和 bullet 里也要做）。
- evidence 值带**参照**让读者判断强弱：`valuation pctile 0.88`（高=贵）这种要么加方向词、要么加阈值/同业对比，别只丢一个裸 0.88。
- `signal_evidence.py` 已经把信号格式化成带值的句子（`20d return 5.2%` 等），好——把方向/着色补上。

---

### IP-6 — 永远带 provenance + recency（来源 + 截至时间）

**Why**：一个信号没有"截至何时、来自哪"，只值一半——读者无法判断它是不是已经过期。

**规则**：每条 evidence / claim 带 as-of 时间和来源；datetime 一律走 `local_time` / `<time>`（见 §6 机器值规则）。

**现状**：signal_groups 的 bullet 没有 as-of / source；hero 有 lifecycle 时间（好），但证据层缺时间戳。

---

### IP-7 — 比较要有 baseline

孤立数字信息量低。**规则**：价格/PnL/仓位尽量给参照并显示 delta——当日 P&L vs 前日、价格 vs 成本、收益 vs benchmark、weight vs target weight。

**现状**：Target Weight 与 Approved Weight 同时展示（`_tab_trades.html:229-240`）——这是好的对照；推广到其它指标。

---

### IP-8 — 按重要性排版；弱化 boilerplate（你没想到的那"别的"）

**Why**：每张卡一样大、每行一样重，读者就抓不到重点。占位文本（"No material update"、"Unavailable"）若和真实信号同等视觉权重，会淹没信号。

**规则**：
- 视觉权重 = 信息重要性。决策 + 风险状态最大；boilerplate 最小（弱灰、或折叠、或干脆隐藏空区块）。
- Timeline 以 **diff（What Changed）** 为主轴，没变化的快照折叠，不要 20 行重复"No material update"（`_tab_trades.html` 的 history 已有 What Changed 段，强化它、弱化无变化项）。
- 同一信息别用两个 label 叠着说（IP-1 提到的 "Trade Decision" + "Latest Conclusion" 双 label）。

---

## 3. Trade 决策视图：建议重排（worked redesign）

把现在 6 张平行卡，按 §1 问题链重组为**自上而下的叙事**：

```
┌ HERO ───────────────────────────────────────────────┐
│ AAPL · LONG            conviction ▮▮▮▮▯ 0.62          │  ← 决策 + 信心(条形)
│ Approved 4.0% (target 5.0%) · Risk: Approved          │  ← 仓位(带 baseline) + 风险状态
│ "一句话 thesis"                                        │  ← 主旨
└───────────────────────────────────────────────────────┘
┌ RATIONALE & EVIDENCE ───────────────────────────────┐  ← IP-2 合并卡：论点+内联证据
│ [BULL] claim … ├ evidence(值·来源·时间) …             │
│ [BEAR] claim … └ evidence …                           │
└───────────────────────────────────────────────────────┘
┌ INVALIDATORS ───────────────────────────────────────┐  ← 什么会推翻它(带触发状态)
└───────────────────────────────────────────────────────┘
┌ PLAN & RISK ────────────────────────────────────────┐  ← entry/exit/max-loss/horizon + risk manager
└───────────────────────────────────────────────────────┘
┌ TIMELINE (diff-first, 折叠) ─────────────────────────┐  ← 怎么演变到今天
└───────────────────────────────────────────────────────┘
```

字段映射 / 成本：

| 区块 | 数据来源 | 成本 |
|---|---|---|
| Hero 决策/信心/仓位/风险 | 现成（trade_decision, confidence, approved/target weight, risk_summary） | 纯模板（加 confidence 条形） |
| Thesis | 现成（trade_plan.thesis） | 纯模板 |
| **Rationale ↔ evidence 关联** | **需数据改动**（建立 driver→signal 引用） | presenter + 数据；过渡期先合并 Bull-Bear + Signal Groups 为一卡 |
| Invalidators | 现成（invalidators 字符串） | 纯模板；"是否触发"需新逻辑（当前无 veto/gate 概念，见 ui-redesign-plan Future Work） |
| Plan & Risk | 现成（entry/exit/max_loss/horizon/risk） | 纯模板 |
| Timeline | 现成（detail.tabs.timeline + What Changed） | 纯模板（弱化无变化项） |
| 删除 trade_plan.edge | 与 bull_points 重复（IP-3） | presenter 去重 |

---

## 4. PnL / 图表交互规格

数据点已在 `today_portfolio_analytics.py` 算好（`equity_chart.points` / `pnl_chart`），几何是 inline SVG。要把它从"静态形状"升级成"可追问"：

- **PnL 用折线图**（不是裸数字、不是只有柱）：已有 `.equity-line` polyline，保持 `fill:none`。
- **逐日 hover**：加一段 vanilla JS（仿照 `base.html` 已有的 inline `<script>` 风格，无需框架）——监听 SVG `mousemove`，按 x 找最近数据点，显示 tooltip（日期 + equity + 当日 P&L + %）+ 竖线 crosshair。数据点坐标已知，presenter 额外吐一个 `points: [{x,y,date,equity,day_pnl,pnl_pct}]` 供 JS 读取（`data-*` 或内联 JSON）。
- **每日 P&L**：与 equity 同图 hover 出当日值即可，不必再单独堆一排柱（避免 IP-8 的等权噪声）；若保留柱，pos/neg 着色 + hover 值。
- **degenerate 兜底**（必须，放 presenter 单测）：单点、全等值、全 0、None、极端区间都要画出合理东西，**绝不除以 0 区间**。`test_today_portfolio_analytics.py` 已建，新增交互不改变这条。
- **改完看渲染**：图表是第一个该看实际渲染结果的东西；hover 行为必须在浏览器里验证或截图。

---

## 5. 视觉系统：收敛到扁平灰蓝（从属）

方向已定（§0.2）。把 Today 的"暖金 + 重阴影 + 超大圆角"退役，向旧页面的扁平灰蓝靠拢：

- **配色**：退掉 KPI/operator/hero 的金棕渐变（`#fffdf8→#f5f0e4`、`#7a5a39`、`#8b5e3c`），统一到旧调色板（`#1a1a2e` 强调、`#f5f5f5` 背景、`#fff` 卡、`#e0e0e0` 边、灰阶文字）。
- **卡片**：所有 surface 收敛到 `.card` 的视觉（白底、1px `#e0e0e0` 边、`--radius-sm` 6px、`--shadow-1`）。退掉 `trades-canvas`/`secondary-surface`/`ticker-detail-hero` 的渐变。
- **阴影**：只留 2 级（`--shadow-1` 贴地、`--shadow-2` 抬起），退掉 `0 16~38px` 的重投影。
- **圆角**：收敛 10 种值 → 4 档（sm 6 / md 12 / lg 16 / pill 999）。
- **建 token**：在 `style.css` 顶部加 `:root`（现状 **0 个 CSS 变量、141 个硬编码颜色、10 种圆角**），新代码只引用 token。基准用灰蓝：

```css
:root{
  --bg:#f5f5f5; --surface:#fff; --surface-muted:#f9f9f9;
  --border:#e0e0e0; --border-soft:#eee;
  --text:#1a1a1a; --text-muted:#666; --text-faint:#888;
  --accent:#1a1a2e; --pos:#1a7f37; --neg:#b42318; --warn:#856404;
  --radius-sm:6px; --radius-md:12px; --radius-lg:16px; --radius-pill:999px;
  --shadow-1:0 2px 4px rgba(0,0,0,.04); --shadow-2:0 6px 16px rgba(0,0,0,.08);
  --space-1:.25rem;--space-2:.5rem;--space-3:.75rem;--space-4:1rem;--space-6:1.5rem;
}
```

迁移分批：先建 token + 新代码强制用 → 再"一次一类"替换旧值（先阴影、再圆角、再颜色）。别一把梭。

---

## 6. 机器值 / 类 / 无障碍（沿用 ui-development skill，复述要点 + 现状违例）

- **机器值**：datetime→`local_time`/`<time>`；数字→`fmt_*`/`pct`；ID/enum→humanize 或隐藏。
  违例：`_tab_risk_macro.html:19` 用 `"%.2f%%"|format` 而非 `pct()`；`_tab_system.html:55/71` 裸 `strategy_id`；`_tab_overview.html:169`/`_tab_risk_macro.html:141` 裸 `severity` enum。
- **每个 class 要有 CSS**：违例（确认）——`_tab_portfolio.html:149/170/191` 用了 `attention-feed-row-review/-alert/-signal`，但 `style.css` 只有基类无变体，三种 attention 行视觉零区分。补规则或删类。
- **无障碍**：`:focus` 当前只在 input/select。给当卡片用的 `<a>`（`.ticker-card`/`.attention-feed-row`/`.detail-list-item`）和 tab 加 `:focus-visible` 焦点环；新文字颜色过 WCAG AA 对比。

---

## 6.5 全局 / 系统性问题（whole-app，不是单个 bug）

退一步看整个 trading app，还有几类**结构性**问题——它们不在某一行代码里，而是贯穿全站：

- **IP-9 数据新鲜度 / 是否 live（trading app 第一问）**：server-rendered = 静态快照，无自动刷新、无"数据截至 HH:MM / 已过期 N 分钟"全局提示。header 有 `market_phase` + 单条 recency，但没有页面级"as-of + 是否实时"。交易工具里"这数据多新、是不是 live"是最该第一眼看到的。**规则**：页面级 as-of 时间戳 + live/stale 状态 + 过期高亮（盘中数据超过阈值变灰/告警）。
- **IP-10 导航要有 attention scent**：tab 现在只有文字 label（`today.html:61`），看不出哪个 tab 有事。`header.open_alert_count` 等数据已存在，却没挂到 tab 上。**规则**：tab 上带计数/红点——`Candidates (3)`、`Risk & Macro ⚠`——让操作者不点就知道去哪。
- **负数货币格式 bug（渲染确认）**：`fmt_currency(-8000.32)` → `$-8,000.32`，负号位置错，应为 `-$8,000.32`。影响每个负的美元值（worst day、亏损、负 P&L）。**规则**：`filters.py` 修 `fmt_currency`，负号提到 `$` 前（或用括号 `($8,000.32)` 会计惯例）。
- **财务数字未右对齐 / 非等宽数字**：表格数字默认左对齐、比例字体（`style.css` 无 `text-align:right` / `tabular-nums`），一列美元值对不齐、难扫读。**规则**：数值列右对齐 + `font-variant-numeric: tabular-nums`。
- **红绿色盲安全**：盈亏只靠红/绿区分对约 8% 男性不可读。现在已带正负号（好），但**规则**：颜色之外再加方向符号/箭头，别只靠红绿。
- **跨 tab 同一实体一致性**：一个 ticker 散落在 Trades / Portfolio / Candidates / Risk 多个 tab，表示方式/可点深链是否一致？**规则**：ticker 应有统一的呈现与 canonical drill-down，不要每个 tab 各画一套。

**已定（产品意图）**：这是一个**面向自动化系统的观察 / 审计界面**——除了"**加 ticker candidate**"（Candidates 的 manual request 表单 + Watchlist 添加）这一步是人工可操作，其余全部自动化(信号→候选→决策→风控→执行均由系统跑)。**不需要** approve / override / 下单 / 撤单等操作交互。

这条产品意图反过来定义了整个 UI 的设计目标：

- **UI 的工作是"让人看懂并信任自动化的判断",不是"让人操作"。** 所以 §1–§4 的信息呈现(尤其 **IP-2 论点↔证据**)是重中之重——人的角色是**审计**系统为什么这么决策,而不是自己拍板。证据链断裂 = 人无法判断该不该信任系统 = UI 失败。
- **唯一的人工动作要显眼且独一份。** "加 ticker candidate"是全站唯一的写操作,应该有清晰、一致的入口(现在散在 Candidates 表单 + Watchlist 两处),不要淹没在只读内容里;反过来其余界面**不应该长得像能点的按钮**(避免误导用户以为能操作)。
- **既然是观察界面,IP-9 数据新鲜度更关键**:人盯的是自动化的实时产出,"这快照多新 / 系统是否在跑"必须一眼可见。

---

## 7. 修复 Backlog（按优先级）

| # | 优先级 | 类别 | 问题 | 位置 | 动作 |
|---|---|---|---|---|---|
| 1 | P0 | 信息 | 论点与证据跨 4 张卡无关联 | trades detail | 过渡：合并 Bull-Bear+Signal Groups 为一卡；终态：建 claim→signal 数据关联（IP-2） |
| 2 | P0 | 信息 | edge==bull_points 重复渲染 | `today_workspace_detail.py:127/132` | presenter 去重，删 Trade Plan 的 Edge 段 |
| 3 | P0 | 交互 | PnL 无逐日 hover | portfolio + analytics presenter | presenter 吐带值数据点 + vanilla JS hover tooltip（§4） |
| 4 | P0 | 视觉 | attention-feed 变体类无 CSS | `_tab_portfolio.html:149/170/191` | 补规则或删类 |
| 5 | P0 | 导航 | Overview tab 接回 | `today.py` `_TAB_LABELS` | 加 `overview`，激活死分支 |
| 6 | P1 | 信息 | confidence/weight 无量级直觉 | hero | 数字旁加进度条；pos/neg 着色 |
| 7 | P1 | 信息 | timeline 无变化项噪声 | trades history | 以 What Changed 为主轴，折叠/弱化无变化快照 |
| 8 | P1 | 机器值 | 裸 slug/ID 当 label（渲染确认，跨 3 tab） | risk manager 卡 / risk-config / system 策略 | humanize 或加 `*_label`：`own_event`/`macro_high_overlay`/`single_name_limit`/`event_window_check`/`risk_config_resolver_v1`/`earnings_drift_v1`/`semis_readthrough_v1`/`market_bars` |
| 9 | P1 | 机器值 | `pct()` 给敞口/保证金强加 `+` 号（误导） | KPI 头 net/gross/margin | 新增不带符号的 `pct_unsigned`（或 `fmt_pct(value, signed=False)`），敞口/占用类用它 |
| 10 | P1 | 信息 | hero 两个 eyebrow 叠着（Trade Decision + Latest Conclusion） | `_tab_trades.html:96-97` | 删一个，保留单一标签 |
| 11 | P1 | 图表 | equity/PnL 图无 Y 轴刻度/数值 | portfolio 图表 | presenter 吐 min/max/baseline 标注，SVG 加轴标签 |
| 12 | P1 | 机器值 | 裸 enum、`format` 替代 `pct()` | system/risk/overview | humanize / 加 `*_label` / 改 `pct()` |
| 13 | P1 | 无障碍 | 链接/卡片/tab 无焦点样式 | 全局 | 加 `:focus-visible` |
| 14 | P1 | 机器值 | 负数货币 `$-8,000.32` 负号位置错 | `filters.py` `fmt_currency` | 负号提到 `$` 前 → `-$8,000.32` |
| 15 | P1 | 导航 | tab 无 attention 计数/红点 | `today.html:61` | tab label 挂 count（数据已在 header） |
| 16 | P2 | 信息 | 全站无 as-of / live-stale 提示 | header | 页面级时间戳 + 过期高亮（IP-9） |
| 17 | P2 | 视觉 | 财务数字未右对齐 / 非 tabular-nums | 表格 | 数值列右对齐 + `tabular-nums` |
| 18 | P2 | 无障碍 | 盈亏只靠红绿（色盲不可读） | 全站 pos/neg | 颜色 + 方向符号/箭头 |
| 19 | P2 | 视觉 | 暖金系收敛到扁平灰蓝 + 建 token | `style.css` 全站 | 分批，先 token 后替换（§5） |
| 20 | P3 | 信息 | invalidator 触发状态 | decision 逻辑 | 需新 gate/veto 逻辑（Future Work，独立项） |

---

## 8. 合并前自检清单（每次改模板/CSS/presenter）

**信息呈现**
1. 视图能按问题链回答吗（决策→为什么→证据→什么推翻→计划→演变）？
2. 每个论点旁边能看到支撑它的证据吗？还是论点和证据分散在不同卡？
3. 同一份内容有没有在两处重复渲染？
4. 数字/图表能被追问吗（hover 出具体值、可展开），还是只是静态摆着？
5. 盈亏/涨跌有没有方向 + 着色 + baseline 对照？
6. evidence 有没有来源 + 截至时间？
7. 占位文本（"No material update"）是不是被弱化了，没和真信号抢视觉权重？

**视觉 / 机制**（沿用 ui-development skill）
8. **看渲染结果**（运行 app 或要截图）——不要凭读 diff 宣称完成；图表/hover 必须实测。
9. 新值来自 token 吗？新 class 在 CSS 里有匹配规则吗？
10. 机器值都过了 filter？当卡片用的 `<a>` 有 `text-decoration:none` + 焦点样式？
11. 图表 `fill:none` + 按 x 排序 + degenerate 兜底 + presenter 单测？
12. presenter 有测试就跑（dedup/格式化/图表数学都可单测，不用浏览器）。

---

## 9. 与 review backlog（[../review_backlog.md](../review_backlog.md)）的关系：哪些 backlog 因这套 UI 设计变简单

把 future-work 的 backlog 套到"观察/审计界面 + 本 guide"上看，有几项**缩小了 / 决策变清晰 / UI 部分基本免费**：

| future-work 项 | 因 UI 设计的影响 | 怎么变简单 |
|---|---|---|
| **#3 UI 难懂** | **从"开放问题"变成"已 spec"** | #3 整项就是这份 guide：(a) label-map/机器值 = §6 + §0.5 的 slug 清单；(b) "today health bar" = IP-9/IP-10；(c) "conclusion→why→evidence" = IP-1/IP-2 + §3 重排。不用再想"怎么让它简单",照 guide 做即可 |
| **#1/#2 observability（让静默 skip 可见）** | **后端出 reason code,UI 半边免费** | 最难的产品问题"怎么把'为什么什么都没发生'显示出来",guide 已给现成落点:today health bar（orders submitted/skipped(reason)/reflection ran?）+ per-tab attention 计数 + as-of/stale。后端只需持久化带 reason 的 skipped 记录,**不用再设计新界面**,喂给 health bar 即可 |
| **#8 Historical Replay 接产 / 的 UI 部分** | **复用现成审计组件,不需要新屏** | replay 产出的是 `candidate_outcome_evaluations`(带 `historical_replay_run_id`),和**实时决策的事后评估同形状**。Candidates tab 已有 evaluation-timeline / history-card / claim↔evidence 组件;replay 结果直接灌进去即可。"在 UI surface replay outcomes"这个子任务大幅缩小。且本就是观察界面的本职(事后审计决策) |
| **#5 LLM prompt logging（接 or 删）** | **观察界面意图让决策更清晰** | UI 是观察面,System tab 已有 LLM spend/usage。prompt 级日志若不打算 surface 给观察者,就是死重 → 倾向**删**(除非要做离线 debug)。产品决策因此更好下 |
| **(隐性) 一整类操作型 UI work** | **被"观察界面"决策直接消除** | 因为只读(只有 add candidate 可操作),**不需要**建 approve/override/下单/撤单的 action→确认→回执流、乐观更新、undo、权限门控等。这一大片潜在 future-work 根本不会出现 |

**UI 设计帮不上的**（纯后端/数据完整性,别指望 UI 简化）：#4 JSON→列、#6 God Repository 拆分、#7 全表扫描+时区 query、各 God 文件拆分。这些该按 future-work 自己的顺序走。

> 一句话：UI 设计把 **#3 从"模糊"变"已 spec"**,把 **#1/#2 和 #8 的 UI 半边变成"复用现成组件 / 填已设计好的 health bar"**,并因"观察界面"定位**消除了一整类操作型交互**的未来工。后端可靠性/数据模型的活不受影响。
