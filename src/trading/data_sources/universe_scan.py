"""Universe scan workflow."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable

from src.trading.data_sources.universe import (
    UniverseFilterConfig,
    UniverseProvider,
    UniverseSnapshotResult,
    apply_universe_filters,
)


class UniverseScanPipeline:
    """Load provider assets and persist deterministic filter decisions."""

    def __init__(
        self,
        *,
        provider: UniverseProvider,
        config: UniverseFilterConfig,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self.provider = provider
        self.config = config
        self.now = now or (lambda: datetime.now(timezone.utc))

    def run(self) -> UniverseSnapshotResult:
        return apply_universe_filters(
            self.provider.fetch_universe_assets(),
            self.config,
            snapshot_time=self.now(),
        )
