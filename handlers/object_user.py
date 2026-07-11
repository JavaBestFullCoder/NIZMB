from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from filters import IsObjectUser
from keyboards import manager_menu, employee_menu, cancel_keyboard, back_keyboard
from database import (
    get_user_by_telegram, get_object,
    create_transaction, get_object_balance, link_transfers,
)
from states import AddIncome, AddExpense, ReportPeriod
from services.balance import get_object_balance_text, get_daily_summary_text
from services.reports import generate_object_report_text
from utils import parse_amount, parse_date, format_amount, format_date, today_str

router = Router()
router.message.filter(IsObjectUser())
router.callback_query.filter(IsObjectUser())


def _get_menu(role: str):
    return manager_menu() if role == "manager" else employee_menu()


async def _get_user_object(user: dict) -> dict | None:
    if user["object_id"]:
        return await get_object(user["object_id"])
    return None


# --- Cancel / Back ---
@router.message(F.text == "❌ Отмена")
async def cancel_operation(message: Message, state: FSMContext):
    await state.clear()
    user = await get_user_by_telegram(message.from_user.id)
    await message.answer("❌ Отменено", reply_markup=_get_menu(user["role"]))


@router.message(F.text == "🔙 Назад")
async def back_to_object_menu(message: Message, state: FSMContext):
    await state.clear()
    user = await get_user_by_telegram(message.from_user.id)
    await message.answer("🏢 Меню", reply_markup=_get_menu(user["role"]))


# --- Income ---
@router.message(F.text == "💰 Приход")
async def income_start(message: Message, state: FSMContext):
    await state.set_state(AddIncome.waiting_for_amount)
    await message.answer(
        "💰 **Добавление прихода**\n\nВведите сумму:",
        reply_markup=cancel_keyboard(),
        parse_mode="Markdown",
    )


@router.message(AddIncome.waiting_for_amount)
async def income_amount(message: Message, state: FSMContext):
    amount = parse_amount(message.text)
    if amount is None:
        await message.answer("❌ Неверная сумма. Введите число больше 0:")
        return
    await state.update_data(inc_amount=amount)
    await state.set_state(AddIncome.waiting_for_date)
    await message.answer(
        f"Сумма: {format_amount(amount)} сум\n\n"
        "Введите **дату** (ДД.ММ.ГГГГ) или 0 для сегодня:",
        parse_mode="Markdown",
    )


@router.message(AddIncome.waiting_for_date)
async def income_date(message: Message, state: FSMContext):
    date = parse_date(message.text)
    if date is None:
        await message.answer("❌ Неверный формат даты. Используйте ДД.ММ.ГГГГ или 0:")
        return
    data = await state.get_data()
    user = await get_user_by_telegram(message.from_user.id)
    date_str = date.strftime("%Y-%m-%d")
    await create_transaction(
        object_id=user["object_id"],
        user_id=user["id"],
        type_="income",
        amount=data["inc_amount"],
        date_str=date_str,
    )
    await state.clear()
    await message.answer(
        f"✅ Приход за {format_date(date_str)}: {format_amount(data['inc_amount'])} сум",
        reply_markup=_get_menu(user["role"]),
    )


# --- Expense types ---
_EXPENSE_LABELS = {
    "expense": ("💸 Расход", "✅ Расход"),
    "director_expense": ("👔 Расход Директора", "✅ Расход Директора"),
    "supplier_payment": ("📦 Оплата поставщика", "✅ Оплата поставщика"),
}


async def _expense_start(message: Message, state: FSMContext, exp_type: str):
    label, _ = _EXPENSE_LABELS.get(exp_type, ("Расход", "Расход"))
    await state.update_data(exp_type=exp_type)
    await state.set_state(AddExpense.waiting_for_amount)
    await message.answer(
        f"{label}\n\nВведите сумму:",
        reply_markup=cancel_keyboard(),
        parse_mode="Markdown",
    )


@router.message(F.text == "💸 Расход")
async def expense_start(message: Message, state: FSMContext):
    await _expense_start(message, state, "expense")


@router.message(F.text == "👔 Расход Директора")
async def director_expense_start(message: Message, state: FSMContext):
    await _expense_start(message, state, "director_expense")


@router.message(F.text == "📦 Оплата поставщика")
async def supplier_payment_start(message: Message, state: FSMContext):
    await _expense_start(message, state, "supplier_payment")


@router.message(AddExpense.waiting_for_amount)
async def expense_amount(message: Message, state: FSMContext):
    amount = parse_amount(message.text)
    if amount is None:
        await message.answer("❌ Неверная сумма. Введите число больше 0:")
        return
    await state.update_data(exp_amount=amount)
    await state.set_state(AddExpense.waiting_for_reason)
    await message.answer(
        f"Сумма: {format_amount(amount)} сум\n\nВведите **причину**:",
        parse_mode="Markdown",
    )


@router.message(AddExpense.waiting_for_reason)
async def expense_reason(message: Message, state: FSMContext):
    reason = message.text.strip()
    if len(reason) < 2:
        await message.answer("❌ Укажите причину (минимум 2 символа):")
        return
    await state.update_data(exp_reason=reason)
    await state.set_state(AddExpense.waiting_for_date)
    await message.answer(
        "Введите **дату** (ДД.ММ.ГГГГ) или 0 для сегодня:",
        reply_markup=back_keyboard(),
    )


@router.message(AddExpense.waiting_for_date)
async def expense_date(message: Message, state: FSMContext):
    date = parse_date(message.text)
    if date is None:
        await message.answer("❌ Неверный формат даты. Используйте ДД.ММ.ГГГГ или 0:")
        return
    data = await state.get_data()
    user = await get_user_by_telegram(message.from_user.id)
    date_str = date.strftime("%Y-%m-%d")
    exp_type = data.get("exp_type", "expense")
    await create_transaction(
        object_id=user["object_id"],
        user_id=user["id"],
        type_=exp_type,
        amount=data["exp_amount"],
        reason=data["exp_reason"],
        date_str=date_str,
    )
    await state.clear()
    _, label_done = _EXPENSE_LABELS.get(exp_type, ("", "✅ Расход"))
    await message.answer(
        f"{label_done} за {format_date(date_str)}:\n"
        f"Сумма: {format_amount(data['exp_amount'])} сум\n"
        f"Причина: {data['exp_reason']}",
        reply_markup=_get_menu(user["role"]),
    )


# --- Transfer to HQ ---
@router.message(F.text == "🔄 Перевод в офис")
async def transfer_start(message: Message, state: FSMContext):
    user = await get_user_by_telegram(message.from_user.id)
    obj = await _get_user_object(user)
    if not obj:
        await message.answer("❌ Объект не найден.")
        return
    balance = await get_object_balance(user["object_id"])
    if balance <= 0:
        await message.answer(f"❌ На счету объекта «{obj['name']}» нет средств. Текущий баланс: {format_amount(balance)} сум")
        return

    await state.update_data(transfer_amount=balance, transfer_obj_id=obj["id"], transfer_obj_name=obj["name"])
    await message.answer(
        f"🔄 **Перевод в головной офис**\n\n"
        f"Объект: «{obj['name']}»\n"
        f"Сумма перевода: {format_amount(balance)} сум\n\n"
        f"Подтвердите перевод:",
        reply_markup=(await _confirm_transfer_kb()),
        parse_mode="Markdown",
    )


async def _confirm_transfer_kb():
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Подтвердить", callback_data="confirm_transfer")
    builder.button(text="❌ Отмена", callback_data="cancel_transfer")
    builder.adjust(2)
    return builder.as_markup()


@router.callback_query(F.data == "confirm_transfer")
async def transfer_confirm(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if not data:
        await callback.answer("Ошибка: данные не найдены", show_alert=True)
        return
    user = await get_user_by_telegram(callback.from_user.id)
    amount = data["transfer_amount"]
    obj_id = data["transfer_obj_id"]
    today = today_str()
    user_id = user["id"]

    out_id = await create_transaction(
        object_id=obj_id,
        user_id=user_id,
        type_="transfer_out",
        amount=amount,
        date_str=today,
    )
    in_id = await create_transaction(
        object_id=None,
        user_id=user_id,
        type_="transfer_in",
        amount=amount,
        date_str=today,
    )
    await link_transfers(out_id, in_id, obj_id)
    await state.clear()
    await callback.message.edit_text(
        f"✅ Перевод выполнен!\n\n"
        f"Объект: «{data['transfer_obj_name']}»\n"
        f"Сумма: {format_amount(amount)} сум\n"
        f"Дата: {format_date(today)}"
    )
    await callback.message.answer("🏢 Меню", reply_markup=_get_menu(user["role"]))


@router.callback_query(F.data == "cancel_transfer")
async def transfer_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    user = await get_user_by_telegram(callback.from_user.id)
    await callback.message.edit_text("❌ Перевод отменен.")
    await callback.message.answer("🏢 Меню", reply_markup=_get_menu(user["role"]))





# --- Reports ---
@router.message(F.text == "📊 Отчеты")
async def object_report_start(message: Message, state: FSMContext):
    user = await get_user_by_telegram(message.from_user.id)
    obj = await _get_user_object(user)
    if not obj:
        await message.answer("❌ Объект не найден.")
        return
    await state.update_data(report_obj_id=obj["id"], report_obj_name=obj["name"])
    await state.set_state(ReportPeriod.waiting_for_start)
    await message.answer(
        "📊 **Отчет по объекту**\n\nВведите **начальную дату** (ДД.ММ.ГГГГ):",
        reply_markup=cancel_keyboard(),
        parse_mode="Markdown",
    )


@router.message(ReportPeriod.waiting_for_start, IsObjectUser())
async def object_report_start_date(message: Message, state: FSMContext):
    date = parse_date(message.text)
    if date is None:
        await message.answer("❌ Неверный формат. Используйте ДД.ММ.ГГГГ:")
        return
    await state.update_data(report_start=date.strftime("%Y-%m-%d"))
    await state.set_state(ReportPeriod.waiting_for_end)
    await message.answer("Введите **конечную дату** (ДД.ММ.ГГГГ):", parse_mode="Markdown")


@router.message(ReportPeriod.waiting_for_end, IsObjectUser())
async def object_report_end_date(message: Message, state: FSMContext):
    date = parse_date(message.text)
    if date is None:
        await message.answer("❌ Неверный формат. Используйте ДД.ММ.ГГГГ:")
        return
    data = await state.get_data()
    start = data["report_start"]
    end = date.strftime("%Y-%m-%d")
    obj_id = data["report_obj_id"]
    obj_name = data["report_obj_name"]
    await state.clear()

    msg = await message.answer("⏳ Генерация отчета...")
    try:
        text_report = await generate_object_report_text(obj_id, obj_name, start, end)
        await message.answer(f"📊 **Отчет «{obj_name}»**\n\n{text_report}", parse_mode="Markdown")
        user = await get_user_by_telegram(message.from_user.id)
        await message.answer("🏢 Меню", reply_markup=_get_menu(user["role"]))
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")
    finally:
        await msg.delete()



