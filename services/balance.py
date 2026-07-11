from database import get_object_balance, get_hq_balance, get_daily_summary, get_hq_transactions
from utils import today_str, format_amount, format_date


async def get_object_balance_text(object_id: int, object_name: str) -> str:
    balance = await get_object_balance(object_id)
    return (
        f"💰 Баланс объекта «{object_name}»\n\n"
        f"Текущий остаток: {format_amount(balance)} сум"
    )


async def get_hq_balance_text() -> str:
    balance = await get_hq_balance()
    today = today_str()
    lines = [
        f"💰 **Баланс головного офиса**\n",
        f"Текущий остаток: {format_amount(balance)} сум\n",
    ]
    # Show recent transfers (last 7 days)
    from datetime import datetime, timedelta
    from config import TZ
    week_ago = (datetime.now(TZ) - timedelta(days=7)).strftime("%Y-%m-%d")
    txns = await get_hq_transactions(week_ago, today)
    transfers = [t for t in txns if t["type"] == "transfer_in"]
    if transfers:
        lines.append("📥 **Последние переводы из объектов:**")
        for t in transfers[-5:]:
            source = t.get("source_object_name", "—")
            lines.append(f"  • {source}: +{format_amount(t['amount'])} сум ({format_date(t['transaction_date'])})")
        lines.append("")
    expenses = [t for t in txns if t["type"] == "expense"]
    if expenses:
        lines.append("📤 **Последние расходы:**")
        for t in expenses[-5:]:
            lines.append(f"  • {format_amount(t['amount'])} сум — {t.get('reason', '—')} ({format_date(t['transaction_date'])})")
    return "\n".join(lines)


async def get_daily_summary_text(object_id: int, object_name: str, date_str: str | None = None) -> str:
    if date_str is None:
        date_str = today_str()
    summary = await get_daily_summary(object_id, date_str)
    return (
        f"📊 Сводка за {format_date(date_str)}\n"
        f"Объект: «{object_name}»\n\n"
        f"🔵 Остаток на начало: {format_amount(summary['opening'])} сум\n"
        f"🟢 Приход: +{format_amount(summary['income'])} сум\n"
        f"🔴 Расход: -{format_amount(summary['expense'])} сум\n"
        f"🟡 Перевод в офис: -{format_amount(summary['transfer_out'])} сум\n"
        f"🏁 Остаток на конец дня: {format_amount(summary['closing'])} сум"
    )
