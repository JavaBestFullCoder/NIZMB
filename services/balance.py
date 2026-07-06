from database import get_object_balance, get_hq_balance, get_daily_summary
from utils import today_str, format_amount, format_date


async def get_object_balance_text(object_id: int, object_name: str) -> str:
    balance = await get_object_balance(object_id)
    return (
        f"💰 Баланс объекта «{object_name}»\n\n"
        f"Текущий остаток: {format_amount(balance)} сум"
    )


async def get_hq_balance_text() -> str:
    balance = await get_hq_balance()
    return (
        f"💰 Баланс головного офиса\n\n"
        f"Текущий остаток: {format_amount(balance)} сум"
    )


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
