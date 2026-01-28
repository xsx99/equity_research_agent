"""Query tools for accessing insider trading data."""
from datetime import datetime, timedelta
from typing import List, Optional
from sqlalchemy import func, desc
from src.db.connection import get_session
from src.db.models import InsiderTrade


class InsiderTools:
    """Query interface for insider trading data."""

    def __init__(self, db_url: Optional[str] = None):
        """Initialize tools with optional database URL."""
        if db_url:
            # Allow custom DB URL for testing or different databases
            from sqlalchemy import create_engine
            from sqlalchemy.orm import sessionmaker
            engine = create_engine(db_url)
            self.SessionLocal = sessionmaker(bind=engine)
        else:
            from src.db.connection import SessionLocal
            self.SessionLocal = SessionLocal

    def get_recent_trades(
        self,
        days: int = 7,
        transaction_type: Optional[str] = None,
        min_value: Optional[float] = None
    ) -> List[InsiderTrade]:
        """Get recent insider trades.

        Args:
            days: Number of days to look back
            transaction_type: Filter by type (e.g., 'P' for purchase, 'S' for sale)
            min_value: Minimum transaction value

        Returns:
            List of InsiderTrade objects
        """
        cutoff_date = datetime.now().date() - timedelta(days=days)

        with get_session() as session:
            query = session.query(InsiderTrade).filter(
                InsiderTrade.filing_date >= cutoff_date
            )

            if transaction_type:
                query = query.filter(InsiderTrade.transaction_type == transaction_type)

            if min_value:
                query = query.filter(InsiderTrade.total_value >= min_value)

            return query.order_by(desc(InsiderTrade.filing_date)).all()

    def get_trades_by_ticker(self, ticker: str, days: int = 30) -> List[InsiderTrade]:
        """Get all insider trades for a specific stock.

        Args:
            ticker: Stock ticker symbol
            days: Number of days to look back

        Returns:
            List of InsiderTrade objects
        """
        cutoff_date = datetime.now().date() - timedelta(days=days)

        with get_session() as session:
            return session.query(InsiderTrade).filter(
                InsiderTrade.ticker == ticker.upper(),
                InsiderTrade.filing_date >= cutoff_date
            ).order_by(desc(InsiderTrade.transaction_date)).all()

    def get_trades_by_insider(self, name: str, limit: int = 50) -> List[InsiderTrade]:
        """Get trading history for a specific insider.

        Args:
            name: Insider name (partial match supported)
            limit: Maximum number of results

        Returns:
            List of InsiderTrade objects
        """
        with get_session() as session:
            return session.query(InsiderTrade).filter(
                InsiderTrade.insider_name.ilike(f"%{name}%")
            ).order_by(desc(InsiderTrade.transaction_date)).limit(limit).all()

    def get_large_transactions(
        self,
        min_value: float,
        days: int = 7
    ) -> List[InsiderTrade]:
        """Get large transactions above a threshold.

        Args:
            min_value: Minimum transaction value in dollars
            days: Number of days to look back

        Returns:
            List of InsiderTrade objects
        """
        cutoff_date = datetime.now().date() - timedelta(days=days)

        with get_session() as session:
            return session.query(InsiderTrade).filter(
                InsiderTrade.total_value >= min_value,
                InsiderTrade.filing_date >= cutoff_date
            ).order_by(desc(InsiderTrade.total_value)).all()

    def get_cluster_activity(
        self,
        days: int = 7,
        min_insiders: int = 3
    ) -> List[dict]:
        """Detect multiple insiders trading the same stock.

        Args:
            days: Number of days to look back
            min_insiders: Minimum number of insiders

        Returns:
            List of dicts with ticker, insider_count, and trades
        """
        cutoff_date = datetime.now().date() - timedelta(days=days)

        with get_session() as session:
            # Group by ticker and count distinct insiders
            clusters = session.query(
                InsiderTrade.ticker,
                func.count(func.distinct(InsiderTrade.insider_name)).label('insider_count')
            ).filter(
                InsiderTrade.filing_date >= cutoff_date
            ).group_by(
                InsiderTrade.ticker
            ).having(
                func.count(func.distinct(InsiderTrade.insider_name)) >= min_insiders
            ).all()

            results = []
            for ticker, count in clusters:
                trades = session.query(InsiderTrade).filter(
                    InsiderTrade.ticker == ticker,
                    InsiderTrade.filing_date >= cutoff_date
                ).order_by(desc(InsiderTrade.transaction_date)).all()

                results.append({
                    'ticker': ticker,
                    'insider_count': count,
                    'trades': trades
                })

            return results

    def search_filings(self, query: str, limit: int = 50) -> List[InsiderTrade]:
        """Search filings by name, ticker, or company.

        Args:
            query: Search term
            limit: Maximum number of results

        Returns:
            List of InsiderTrade objects
        """
        with get_session() as session:
            search_pattern = f"%{query}%"
            return session.query(InsiderTrade).filter(
                (InsiderTrade.ticker.ilike(search_pattern)) |
                (InsiderTrade.company_name.ilike(search_pattern)) |
                (InsiderTrade.insider_name.ilike(search_pattern))
            ).order_by(desc(InsiderTrade.filing_date)).limit(limit).all()
