import os
from pathlib import Path

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, FSInputFile
from aiogram.fsm.context import FSMContext

from config import REPORTS_DIR
from filters import IsObjectUser, IsManager
from keyboards import manager_menu, employee_menu, cancel_keyboard, back_keyboard
from database import (
    get_user_by_telegram, get_object, get_employees,
    create_transaction, get_object_balance, link_transfers,
    code_exists, create_access_code,
)
from states import AddIncome, AddExpense, AddEmployee, ReportPeriod
from services.balance import get_object_balance_text, get_daily_summary_text
from services.reports import generate_object_report, generate_object_report_text
from services.google_drive import upload_file, is_configured, setup_instructions
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


# --- Expense ---
@router.message(F.text == "💸 Расход")
async def expense_start(message: Message, state: FSMContext):
    await state.set_state(AddExpense.waiting_for_amount)
    await message.answer(
        "💸 **Добавление расхода**\n\nВведите сумму:",
        reply_markup=cancel_keyboard(),
        parse_mode="Markdown",
    )


@router.message(AddExpense.waiting_for_amount)
async def expense_amount(message: Message, state: FSMContext):
    amount = parse_amount(message.text)
    if amount is None:
        await message.answer("❌ Неверная сумма. Введите число больше 0:")
        return
    await state.update_data(exp_amount=amount)
    await state.set_state(AddExpense.waiting_for_reason)
    await message.answer(
        f"Сумма: {format_amount(amount)} сум\n\nВведите **причину** расхода:",
        parse_mode="Markdown",
    )


@router.message(AddExpense.waiting_for_reason)
async def expense_reason(message: Message, state: FSMContext):
    reason = message.text.strip()
    if len(reason) < 2:
        await message.answer("❌ Укажите причину расхода (минимум 2 символа):")
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
    await create_transaction(
        object_id=user["object_id"],
        user_id=user["id"],
        type_="expense",
        amount=data["exp_amount"],
        reason=data["exp_reason"],
        date_str=date_str,
    )
    await state.clear()
    await message.answer(
        f"✅ Расход за {format_date(date_str)}:\n"
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


# --- Employees (manager only) ---
@router.message(F.text == "👥 Сотрудники", IsManager())
async def manage_employees(message: Message):
    user = await get_user_by_telegram(message.from_user.id)
    obj = await _get_user_object(user)
    if not obj:
        await message.answer("❌ Объект не найден.")
        return
    employees = await get_employees(user["object_id"])
    lines = [f"👥 **Сотрудники «{obj['name']}»**:\n"]
    for emp in employees:
        status = "✅" if emp["telegram_id"] else "❌ (не активирован)"
        lines.append(f"  {status} {emp['name']} ({emp['role']})")
    if not employees:
        lines.append("  Нет сотрудников.")

    from aiogram.utils.keyboard import InlineKeyboardBuilder
    builder = InlineKeyboardBuilder()
    builder.button(text="➕ Добавить код сотрудника", callback_data=f"add_emp_obj_{user['object_id']}")
    builder.adjust(1)
    await message.answer("\n".join(lines), reply_markup=builder.as_markup(), parse_mode="Markdown")


@router.callback_query(F.data.startswith("add_emp_obj_"), IsManager())
async def add_employee_start(callback: CallbackQuery, state: FSMContext):
    obj_id = int(callback.data.split("_")[3])
    obj = await get_object(obj_id)
    if not obj:
        await callback.answer("Объект не найден", show_alert=True)
        return
    await state.update_data(emp_obj_id=obj["id"], emp_obj_name=obj["name"])
    await state.set_state(AddEmployee.waiting_for_code)
    await callback.message.edit_text(
        f"➕ Создание кода сотрудника для «{obj['name']}»\n\n"
        f"Введите **код доступа**, который будут использовать сотрудники:",
        parse_mode="Markdown",
    )


@router.message(AddEmployee.waiting_for_code, IsManager())
async def add_employee_code(message: Message, state: FSMContext):
    code = message.text.strip()
    if await code_exists(code):
        await message.answer("❌ Этот код уже используется. Придумайте другой:")
        return
    if len(code) < 3:
        await message.answer("Код должен быть минимум 3 символа. Попробуйте снова:")
        return
    data = await state.get_data()
    await create_access_code(code, "employee", data["emp_obj_id"])
    await state.clear()
    user = await get_user_by_telegram(message.from_user.id)
    await message.answer(
        f"✅ Код сотрудника создан для «{data['emp_obj_name']}»\n"
        f"Код: `{code}`\n\n"
        f"Сколько угодно человек могут войти по этому коду.",
        parse_mode="Markdown",
        reply_markup=_get_menu(user["role"]),
    )


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
        filepath = await generate_object_report(obj_id, obj_name, start, end)
        text_report = await generate_object_report_text(obj_id, obj_name, start, end)
        await message.answer(f"📊 **Текстовый отчет**\n\n{text_report}", parse_mode="Markdown")
        doc = FSInputFile(filepath)
        await message.answer_document(
            doc,
            caption=f"📊 Отчет «{obj_name}» {format_date(start)} — {format_date(end)}",
        )
        user = await get_user_by_telegram(message.from_user.id)
        await message.answer("🏢 Меню", reply_markup=_get_menu(user["role"]))
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")
    finally:
        await msg.delete()


# --- Google Drive ---
@router.message(F.text == "☁️ Google Диск", IsObjectUser())
async def upload_to_drive(message: Message):
    if not await is_configured():
        await message.answer(
            "❌ Google Диск не настроен.\n\n" + setup_instructions(),
            disable_web_page_preview=True,
        )
        return
    await message.answer(
        "☁️ **Загрузка на Google Диск**\n\n"
        "Отправьте файл .xlsx для загрузки.",
        parse_mode="Markdown",
    )


@router.message(F.document, IsObjectUser())
async def handle_document(message: Message):
    if not await is_configured():
        await message.answer("❌ Google Диск не настроен.")
        return
    file = message.document
    if not file.file_name.endswith(".xlsx"):
        await message.answer("❌ Поддерживаются только .xlsx файлы.")
        return
    msg = await message.answer("⏳ Загрузка на Google Диск...")
    try:
        file_path = os.path.join(REPORTS_DIR, file.file_name or "report.xlsx")
        await message.bot.download(file.file_id, destination=Path(file_path))
        link = await upload_file(file_path)
        if link:
            await msg.edit_text(f"✅ Файл загружен:\n{link}", disable_web_page_preview=True)
        else:
            await msg.edit_text("❌ Ошибка загрузки на Google Диск.")
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {e}")
