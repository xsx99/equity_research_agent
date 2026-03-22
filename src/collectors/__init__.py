"""Data collectors package."""
from src.collectors.base import BaseCollector, CollectionResult
from src.collectors.sec_edgar.collector import SECEdgarCollector

__all__ = ["BaseCollector", "CollectionResult", "SECEdgarCollector"]
