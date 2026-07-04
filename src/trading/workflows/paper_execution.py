"""Compatibility shim for the paper execution workflow."""
from __future__ import annotations

from src.trading.execution.paper_execution import (
    PaperExecutionWorkflow,
    PaperExecutionWorkflowResult,
    _build_option_order_request,
)

__all__ = [
    "PaperExecutionWorkflow",
    "PaperExecutionWorkflowResult",
    "_build_option_order_request",
]
