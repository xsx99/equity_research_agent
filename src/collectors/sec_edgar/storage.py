"""SEC Form 4 storage helpers."""
from datetime import datetime
from typing import Dict, List

from sqlalchemy.dialects.postgresql import insert as pg_insert

from src.db.models import InsiderTrade


def upsert_transactions(session, transactions: List[Dict]) -> int:
    """Upsert a list of transaction dicts into the database.

    Returns the number of rows affected.
    """
    if not transactions:
        return 0

    # De-duplicate by (accession_number, transaction_index)
    unique_rows: Dict[tuple, Dict] = {}
    for transaction in transactions:
        accession_number = transaction.get("accession_number")
        transaction_index = transaction.get("transaction_index")
        if accession_number is None or transaction_index is None:
            continue
        unique_rows[(accession_number, transaction_index)] = transaction

    rows = list(unique_rows.values())
    if not rows:
        return 0

    now = datetime.utcnow()
    for row in rows:
        row.setdefault("created_at", now)

    insert_stmt = pg_insert(InsiderTrade.__table__).values(rows)
    update_cols = {
        col.name: getattr(insert_stmt.excluded, col.name)
        for col in InsiderTrade.__table__.columns
        if col.name not in {"id", "created_at"}
    }
    upsert_stmt = insert_stmt.on_conflict_do_update(
        constraint="uq_insider_trades_accession_txn_index",
        set_=update_cols,
    )

    result = session.execute(upsert_stmt)
    return result.rowcount or 0
