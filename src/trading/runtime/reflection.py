"""Compatibility shim for the reflection phase runtime."""
from __future__ import annotations

import sys

from src.trading.phases import reflection as _canonical

LiveReflectionDependencies = _canonical.LiveReflectionDependencies
LiveReflectionRequestLoader = _canonical.LiveReflectionRequestLoader
LiveReflectionRuntime = _canonical.LiveReflectionRuntime
ReflectionLoadResult = _canonical.ReflectionLoadResult
build_live_reflection_dependencies = _canonical.build_live_reflection_dependencies
run_live_reflection_once = _canonical.run_live_reflection_once
run_reflection_once = _canonical.run_reflection_once

__all__ = [
    "LiveReflectionDependencies",
    "LiveReflectionRequestLoader",
    "LiveReflectionRuntime",
    "ReflectionLoadResult",
    "build_live_reflection_dependencies",
    "run_live_reflection_once",
    "run_reflection_once",
]

_canonical.__all__ = __all__
sys.modules[__name__] = _canonical
