"""Pure portfolio analytics helpers for the today dashboard."""
from __future__ import annotations

from typing import Any, Iterable


def build_portfolio_analytics(
    history: Iterable[dict[str, Any]] | None,
    *,
    width: int = 720,
    height: int = 180,
) -> dict[str, Any] | None:
    series = [_normalize_history_row(row) for row in history or ()]
    series = [row for row in series if row["equity"] is not None]
    if not series:
        return None

    equity_values = [float(row["equity"]) for row in series]
    day_pnls = [float(row["day_pnl"]) for row in series if row["day_pnl"] is not None]
    point_count = len(series)

    plot_left = 18.0
    plot_right = float(width) - 18.0
    plot_top = 18.0
    plot_bottom = float(height) - 24.0
    plot_width = plot_right - plot_left
    plot_height = plot_bottom - plot_top

    equity_min = min(equity_values)
    equity_max = max(equity_values)
    equity_points = _build_equity_points(
        equity_values,
        left=plot_left,
        top=plot_top,
        width=plot_width,
        height=plot_height,
    )

    positive_max = max((value for value in day_pnls if value > 0), default=0.0)
    negative_abs_max = max((-value for value in day_pnls if value < 0), default=0.0)
    if positive_max == 0.0 and negative_abs_max == 0.0:
        baseline_y = plot_top + (plot_height / 2.0)
        day_scale = 0.0
    else:
        scale_denom = positive_max + negative_abs_max
        baseline_y = plot_top + (plot_height * (positive_max / scale_denom)) if scale_denom else plot_top
        day_scale = plot_height / scale_denom if scale_denom else 0.0

    daily_bars, bar_width = _build_daily_bars(
        day_pnls,
        left=plot_left,
        baseline_y=baseline_y,
        width=plot_width,
        plot_height=plot_height,
        scale=day_scale,
    )

    total_return = None
    if equity_values[0]:
        total_return = (equity_values[-1] / equity_values[0]) - 1.0

    max_drawdown = _max_drawdown(equity_values)
    win_days = sum(1 for value in day_pnls if value > 0)
    loss_days = sum(1 for value in day_pnls if value < 0)
    active_days = win_days + loss_days
    profitable_days_pct = (win_days / active_days) if active_days else 0.0
    best_day = max(day_pnls) if day_pnls else None
    worst_day = min(day_pnls) if day_pnls else None
    active_day_pnls = [value for value in day_pnls if value != 0]
    avg_day_pnl = (sum(active_day_pnls) / len(active_day_pnls)) if active_day_pnls else None
    gross_win = sum(value for value in day_pnls if value > 0)
    gross_loss = abs(sum(value for value in day_pnls if value < 0))
    daily_profit_factor = (gross_win / gross_loss) if gross_loss else None

    # Sharpe ratio (annualized, risk-free = 0) from daily equity returns.
    daily_returns = [
        equity_values[i] / equity_values[i - 1] - 1.0
        for i in range(1, len(equity_values))
        if equity_values[i - 1]
    ]
    sharpe_ratio = None
    if len(daily_returns) >= 2:
        mean_return = sum(daily_returns) / len(daily_returns)
        variance = sum((r - mean_return) ** 2 for r in daily_returns) / (len(daily_returns) - 1)
        std_return = variance ** 0.5
        if std_return > 0:
            sharpe_ratio = (mean_return / std_return) * (252 ** 0.5)

    # X-axis date ticks (a few evenly-spaced points) shared by both charts.
    x_axis_ticks: list[dict[str, Any]] = []
    if point_count >= 2:
        tick_count = min(5, point_count)
        seen_idx: set[int] = set()
        for k in range(tick_count):
            idx = round(k * (point_count - 1) / (tick_count - 1))
            if idx in seen_idx:
                continue
            seen_idx.add(idx)
            x_axis_ticks.append(
                {
                    "x": round(plot_left + (idx / (point_count - 1)) * plot_width, 1),
                    "time": series[idx].get("time"),
                    "anchor": "start" if idx == 0 else ("end" if idx == point_count - 1 else "middle"),
                }
            )

    return {
        "point_count": point_count,
        "series": tuple(
            {
                "date": row.get("time"),
                "equity": float(row["equity"]),
                "day_pnl": float(row["day_pnl"]) if row["day_pnl"] is not None else None,
            }
            for row in series
        ),
        "equity_chart": {
            "points": equity_points,
            "min": equity_min,
            "max": equity_max,
        },
        "pnl_chart": {
            "bars": tuple(daily_bars),
            "baseline_y": round(baseline_y, 1),
            "bar_width": round(bar_width, 1),
        },
        "x_axis_ticks": tuple(x_axis_ticks),
        "equity_start": equity_values[0],
        "equity_end": equity_values[-1],
        "equity_min": equity_min,
        "equity_max": equity_max,
        "metrics": {
            "total_return": total_return,
            "max_drawdown": max_drawdown,
            "win_days": win_days,
            "loss_days": loss_days,
            "profitable_days_pct": profitable_days_pct,
            "best_day": best_day,
            "worst_day": worst_day,
            "avg_day_pnl": avg_day_pnl,
            "daily_profit_factor": daily_profit_factor,
            "sharpe_ratio": sharpe_ratio,
        },
    }


def _normalize_history_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "equity": _safe_float(row.get("equity")),
        "day_pnl": _safe_float(row.get("day_pnl")),
        "time": row.get("time"),
    }


def _build_equity_points(
    equity_values: list[float],
    *,
    left: float,
    top: float,
    width: float,
    height: float,
) -> str:
    if len(equity_values) == 1:
        x = left + (width / 2.0)
        y = top + (height / 2.0)
        return f"{x:.1f},{y:.1f}"

    span = max(len(equity_values) - 1, 1)
    minimum = min(equity_values)
    maximum = max(equity_values)
    points: list[str] = []
    for index, value in enumerate(equity_values):
        x = left + (width * index / span)
        if maximum == minimum:
            y = top + (height / 2.0)
        else:
            y = top + (height * (maximum - value) / (maximum - minimum))
        points.append(f"{x:.1f},{y:.1f}")
    return " ".join(points)


def _build_daily_bars(
    day_pnls: list[float],
    *,
    left: float,
    baseline_y: float,
    width: float,
    plot_height: float,
    scale: float,
) -> tuple[list[dict[str, Any]], float]:
    if not day_pnls:
        return [], 0.0

    count = len(day_pnls)
    bar_slot = width / max(count, 1)
    bar_width = max(min(bar_slot * 0.62, 24.0), 2.0)
    bars: list[dict[str, Any]] = []
    for index, value in enumerate(day_pnls):
        center_x = left + (bar_slot * index) + (bar_slot / 2.0)
        height = abs(value) * scale
        positive = value >= 0
        y = baseline_y - height if positive else baseline_y
        bars.append(
            {
                "x": round(center_x - (bar_width / 2.0), 1),
                "y": round(y, 1),
                "w": round(bar_width, 1),
                "h": round(height, 1),
                "positive": positive,
            }
        )
    return bars, bar_width


def _max_drawdown(equity_values: list[float]) -> float:
    if not equity_values:
        return 0.0
    peak = equity_values[0]
    max_drawdown = 0.0
    for value in equity_values:
        if value > peak:
            peak = value
        if peak > 0:
            drawdown = (peak - value) / peak
            if drawdown > max_drawdown:
                max_drawdown = drawdown
    return max_drawdown


def _safe_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
