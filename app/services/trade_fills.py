"""
Trade fills read path (OTA-855): the stored broker transactions as the fill rows the
Short-DTE Trade Lab dashboard reads, with each fill's market context. Shared by the
REST route and the MCP tool so both answer with the same shape. Always user-scoped.
"""

from datetime import date, datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.database import BrokerAccount, BrokerFillContext, BrokerTransaction
from app.services.broker_activity import FILL_COLUMNS, fill_row


def parse_day(text: Optional[str]) -> Optional[date]:
    if not text:
        return None
    return date.fromisoformat(str(text)[:10])


async def list_fill_rows(
    db: AsyncSession,
    user_id: str,
    start: Optional[date] = None,
    end: Optional[date] = None,
    account: Optional[str] = None,
    limit: int = 5000,
) -> dict:
    """Fills for one user, oldest first, in the dashboard's Trades-sheet columns plus context."""
    query = (
        select(BrokerTransaction, BrokerAccount, BrokerFillContext)
        .join(BrokerAccount, BrokerAccount.id == BrokerTransaction.account_id)
        .outerjoin(BrokerFillContext, BrokerFillContext.transaction_id == BrokerTransaction.id)
        .where(BrokerTransaction.user_id == user_id, BrokerTransaction.transaction_type == "TRADE")
        .order_by(BrokerTransaction.time.asc(), BrokerTransaction.id.asc())
    )
    if start:
        query = query.where(BrokerTransaction.time >= datetime.combine(start, datetime.min.time()) - timedelta(days=1))
    if end:
        query = query.where(BrokerTransaction.time < datetime.combine(end, datetime.min.time()) + timedelta(days=2))
    if account:
        query = query.where(BrokerAccount.label == account)
    query = query.limit(max(1, min(int(limit or 5000), 20000)))
    rows = []
    for txn, acct, ctx in (await db.execute(query)).all():
        row = fill_row(txn, ctx, acct.label, settings.broker_activity_display_tz)
        if start and row["trade_date"] < start.isoformat():
            continue
        if end and row["trade_date"] > end.isoformat():
            continue
        rows.append(row)
    for index, row in enumerate(rows, 1):
        row["row"] = str(index)
    return {
        "columns": FILL_COLUMNS,
        "rows": rows,
        "count": len(rows),
        "as_of": datetime.now(timezone.utc).isoformat(),
        "display_tz": settings.broker_activity_display_tz,
        "source": "broker_transactions",
    }
