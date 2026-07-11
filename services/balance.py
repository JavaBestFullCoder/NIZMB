from database import get_object_balance, get_hq_balance, get_daily_summary, get_hq_transactions, get_objects
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
        f"💰 **Баланс головного офиса**",
        f"Текущий остаток: {format_amount(balance)} сум\n",
    ]
    # Show recent transfers (last 7 days)
    from datetime import datetime, timedelta
    from config import TZ
    week_ago = (datetime.now(TZ) - timedelta(days=7)).strftime("%Y-%m-%d")
    txns = await get_hq_transactions(week_ago, today)
    transfers = [t for t in txns if t["type"] == "transfer_in"]
    if transfers:
        lines.append("📥 **Последние переводы:**")
        for t in transfers[-5:]:
            source = t.get("source_object_name", "—")
            lines.append(f"  • {source}: +{format_amount(t['amount'])} сум ({format_date(t['transaction_date'])})")
    expenses = [t for t in txns if t["type"] in ("expense", "director_expense", "supplier_payment")]
    if expenses:
        lines.append("📤 **Последние расходы:**")
        for t in expenses[-5:]:
            lines.append(f"  • {format_amount(t['amount'])} сум — {t.get('reason', '—')} ({format_date(t['transaction_date'])})")

    # All objects balances
    objects = await get_objects()
    if objects:
        lines.append("")
        lines.append("🏢 **Балансы объектов:**")
        total_obj = 0.0
        for obj in objects:
            obj_bal = await get_object_balance(obj["id"])
            total_obj += obj_bal
            lines.append(f"  • {obj['name']}: {format_amount(obj_bal)} сум")
        lines.append("")
        lines.append(f"📊 **Общий остаток (ГО + объекты):** {format_amount(balance + total_obj)} сум")

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
