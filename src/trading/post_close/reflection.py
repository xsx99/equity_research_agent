"""Compatibility shim for post-close reflection records and pipeline."""
from __future__ import annotations

import sys

from src.trading.phases.reflection import pipeline as _canonical

DailyReflectionRecord = _canonical.DailyReflectionRecord
LearningFactorRecord = _canonical.LearningFactorRecord
ReflectionPipeline = _canonical.ReflectionPipeline
ReflectionPipelineRequest = _canonical.ReflectionPipelineRequest
ReflectionPipelineResult = _canonical.ReflectionPipelineResult
derive_learning_factor_status = _canonical.derive_learning_factor_status

__all__ = [
    "DailyReflectionRecord",
    "LearningFactorRecord",
    "ReflectionPipeline",
    "ReflectionPipelineRequest",
    "ReflectionPipelineResult",
    "derive_learning_factor_status",
]

_canonical.__all__ = __all__
sys.modules[__name__] = _canonical
