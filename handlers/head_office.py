from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, FSInputFile
from aiogram.fsm.context import FSMContext

from filters import IsHeadOffice
from keyboards import (
    head_office_menu, objects_inline, object_actions_inline,
    confirm_keyboard, cancel_keyboard, back_keyboard,
)
from database import (
    get_object, get_objects, create_object, delete_object,
    create_transaction, get_object_balance, get_employees,
    code_exists, get_user_by_telegram, create_access_code,
    get_all_codes_with_users,
)
from states import AddObject, AddEmployee, AddExpense, AddHQUser, ReportPeriod
from services.balance import get_hq_balance_text
from services.reports import generate_all_objects_report, generate_object_report, generate_object_report_text
from utils import parse_amount, parse_date, format_amount, format_date, today_str

router = Router()
router.message.filter(IsHeadOffice())
router.callback_query.filter(IsHeadOffice())


@router.message(F.text == "🔙 Назад")
async def back_to_menu(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("🏢 Главное меню", reply_markup=head_office_menu())


@router.message(F.text == "❌ Отмена")
async def cancel_hq(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("❌ Отменено", reply_markup=head_office_menu())


@router.message(F.text == "📋 Управление объектами")
async def manage_objects(message: Message):
    kb = await objects_inline([("➕ Добавить объект", "add_object")])
    await message.answer("📋 **Управление объектами**\nВыберите объект:", reply_markup=kb, parse_mode="Markdown")


@router.callback_query(F.data == "back_to_objects")
async def back_to_objects(callback: CallbackQuery):
    kb = await objects_inline([("➕ Добавить объект", "add_object")])
    await callback.message.edit_text("📋 **Управление объектами**\nВыберите объект:", reply_markup=kb, parse_mode="Markdown")


@router.callback_query(F.data == "back_to_menu")
async def callback_back_to_menu(callback: CallbackQuery):
    await callback.message.delete()
    await callback.message.answer("🏢 Главное меню", reply_markup=head_office_menu())


@router.callback_query(F.data == "add_object")
async def add_object_start(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text("Введите **название объекта**:", parse_mode="Markdown")
    await state.set_state(AddObject.waiting_for_name)


@router.message(AddObject.waiting_for_name)
async def add_object_name(message: Message, state: FSMContext):
    name = message.text.strip()
    if len(name) < 2 or len(name) > 100:
        await message.answer("Название должно быть от 2 до 100 символов. Попробуйте снова:")
        return
    await state.update_data(obj_name=name)
    await state.set_state(AddObject.waiting_for_code)
    await message.answer(f"Объект «{name}»\n\nВведите **код доступа** для менеджера:", reply_markup=back_keyboard(), parse_mode="Markdown")


@router.message(AddObject.waiting_for_code)
async def add_object_code(message: Message, state: FSMContext):
    code = message.text.strip()
    if await code_exists(code):
        await message.answer("❌ Этот код уже используется. Придумайте другой:")
        return
    if len(code) < 3:
        await message.answer("Код должен быть минимум 3 символа. Попробуйте снова:")
        return
    data = await state.get_data()
    obj_name = data["obj_name"]
    obj_id = await create_object(obj_name)
    await create_access_code(code, "manager", obj_id)
    await state.clear()
    await message.answer(
        f"✅ Объект «{obj_name}» создан!\n"
        f"Код менеджера: `{code}`\n\n"
        f"Сколько угодно человек могут войти по этому коду.",
        parse_mode="Markdown",
        reply_markup=head_office_menu(),
    )


@router.callback_query(F.data.startswith("obj_"))
async def object_selected(callback: CallbackQuery):
    obj_id = int(callback.data.split("_")[1])
    obj = await get_object(obj_id)
    if not obj:
        await callback.answer("Объект не найден", show_alert=True)
        return
    balance = await get_object_balance(obj_id)
    text = (
        f"🏢 **{obj['name']}**\n"
        f"💰 Баланс: {format_amount(balance)} сум\n\n"
    )
    kb = await object_actions_inline(obj_id)
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")


@router.callback_query(F.data.startswith("balance_"))
async def show_object_balance(callback: CallbackQuery):
    obj_id = int(callback.data.split("_")[1])
    obj = await get_object(obj_id)
    if not obj:
        await callback.answer("Объект не найден", show_alert=True)
        return
    balance = await get_object_balance(obj_id)
    await callback.message.edit_text(
        f"💰 Баланс **{obj['name']}**: {format_amount(balance)} сум",
        parse_mode="Markdown",
    )
    await callback.message.answer("🔙 Выберите действие:", reply_markup=await object_actions_inline(obj_id))


@router.callback_query(F.data.startswith("employees_"))
async def show_employees(callback: CallbackQuery):
    obj_id = int(callback.data.split("_")[1])
    obj = await get_object(obj_id)
    if not obj:
        await callback.answer("Объект не найден", show_alert=True)
        return
    employees = await get_employees(obj_id)
    if not employees:
        text = f"В «{obj['name']}» нет сотрудников."
    else:
        lines = [f"👥 **Сотрудники «{obj['name']}»**:\n"]
        for emp in employees:
            status = "✅" if emp["telegram_id"] else "❌"
            lines.append(f"  {status} {emp['name']} ({emp['role']})")
        text = "\n".join(lines)
    await callback.message.edit_text(text, parse_mode="Markdown")
    await callback.message.answer("🔙 Выберите действие:", reply_markup=await object_actions_inline(obj_id))


@router.callback_query(F.data.startswith("add_emp_"))
async def add_employee_start(callback: CallbackQuery, state: FSMContext):
    obj_id = int(callback.data.split("_")[2])
    obj = await get_object(obj_id)
    if not obj:
        await callback.answer("Объект не найден", show_alert=True)
        return
    await state.update_data(emp_obj_id=obj_id, emp_obj_name=obj["name"])
    await state.set_state(AddEmployee.waiting_for_code)
    await callback.message.edit_text(
        f"➕ Создание кода сотрудника для «{obj['name']}»\n\n"
        f"Введите **код доступа**, который будут использовать сотрудники:",
        parse_mode="Markdown",
    )


@router.message(AddEmployee.waiting_for_code)
async def add_employee_code(message: Message, state: FSMContext):
    code = message.text.strip()
    if await code_exists(code):
        await message.answer("❌ Этот код уже используется. Придумайте другой:")
        return
    if len(code) < 3:
        await message.answer("Код должен быть минимум 3 символа. Попробуйте снова:")
        return
    data = await state.get_data()
    await create_access_code(code, "manager", data["emp_obj_id"])
    await state.clear()
    await message.answer(
        f"✅ Код менеджера создан для «{data['emp_obj_name']}»\n"
        f"Код: `{code}`\n\n"
        f"Сколько угодно человек могут войти по этому коду.",
        parse_mode="Markdown",
        reply_markup=head_office_menu(),
    )


@router.callback_query(F.data.startswith("del_obj_"))
async def delete_object_confirm(callback: CallbackQuery, state: FSMContext):
    obj_id = int(callback.data.split("_")[2])
    obj = await get_object(obj_id)
    if not obj:
        await callback.answer("Объект не найден", show_alert=True)
        return
    await state.update_data(del_obj_id=obj_id)
    await callback.message.edit_text(
        f"⚠️ **Удалить объект «{obj['name']}»?**\n\n"
        f"Будут удалены:\n"
        f"• Все сотрудники объекта\n"
        f"• Все транзакции\n\n"
        f"Это действие **необратимо**.",
        parse_mode="Markdown",
        reply_markup=confirm_keyboard("delete_object", str(obj_id)),
    )


@router.callback_query(F.data.startswith("confirm_delete_object_"))
async def delete_object_execute(callback: CallbackQuery, state: FSMContext):
    obj_id = int(callback.data.split("_")[3])
    obj = await get_object(obj_id)
    if obj:
        await delete_object(obj_id)
        await callback.message.edit_text(f"✅ Объект «{obj['name']}» удален.")
    else:
        await callback.message.edit_text("❌ Объект не найден.")
    await state.clear()


@router.message(F.text == "💰 Мой счет")
async def hq_balance(message: Message):
    text = await get_hq_balance_text()
    await message.answer(text, parse_mode="Markdown")


# --- HQ Expense types ---
_HQ_EXPENSE_LABELS = {
    "expense": ("💸 Расход", "✅ Расход ГО"),
    "director_expense": ("👔 Расход Директора", "✅ Расход Директора ГО"),
    "supplier_payment": ("📦 Оплата поставщика", "✅ Оплата поставщика ГО"),
}


async def _hq_expense_start(message: Message, state: FSMContext, exp_type: str):
    label, _ = _HQ_EXPENSE_LABELS.get(exp_type, ("Расход", "Расход"))
    await state.update_data(exp_type=exp_type)
    await state.set_state(AddExpense.waiting_for_amount)
    await message.answer(
        f"{label}\n\nВведите **сумму** для головного офиса:",
        reply_markup=cancel_keyboard(),
        parse_mode="Markdown",
    )


@router.message(F.text == "💸 Расход")
async def hq_expense_start(message: Message, state: FSMContext):
    await _hq_expense_start(message, state, "expense")


@router.message(F.text == "👔 Расход Директора")
async def hq_director_expense_start(message: Message, state: FSMContext):
    await _hq_expense_start(message, state, "director_expense")


@router.message(F.text == "📦 Оплата поставщика")
async def hq_supplier_payment_start(message: Message, state: FSMContext):
    await _hq_expense_start(message, state, "supplier_payment")


@router.message(AddExpense.waiting_for_amount, IsHeadOffice())
async def hq_expense_amount(message: Message, state: FSMContext):
    amount = parse_amount(message.text)
    if amount is None:
        await message.answer("❌ Неверная сумма. Введите число больше 0:")
        return
    await state.update_data(exp_amount=amount)
    await state.set_state(AddExpense.waiting_for_reason)
    await message.answer(f"Сумма: {format_amount(amount)} сум\n\nВведите **причину**:", parse_mode="Markdown")


@router.message(AddExpense.waiting_for_reason, IsHeadOffice())
async def hq_expense_reason(message: Message, state: FSMContext):
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


@router.message(AddExpense.waiting_for_date, IsHeadOffice())
async def hq_expense_date(message: Message, state: FSMContext):
    date = parse_date(message.text)
    if date is None:
        await message.answer("❌ Неверный формат даты. Используйте ДД.ММ.ГГГГ или 0:")
        return
    data = await state.get_data()
    user = await get_user_by_telegram(message.from_user.id)
    date_str = date.strftime("%Y-%m-%d")
    exp_type = data.get("exp_type", "expense")
    await create_transaction(
        object_id=None,
        user_id=user["id"],
        type_=exp_type,
        amount=data["exp_amount"],
        reason=data["exp_reason"],
        date_str=date_str,
    )
    await state.clear()
    _, label_done = _HQ_EXPENSE_LABELS.get(exp_type, ("", "✅ Расход ГО"))
    await message.answer(
        f"{label_done} за {format_date(date_str)}:\n"
        f"Сумма: {format_amount(data['exp_amount'])} сум\n"
        f"Причина: {data['exp_reason']}",
        reply_markup=head_office_menu(),
    )


@router.message(F.text == "📊 Отчеты за период")
async def report_period_start(message: Message, state: FSMContext):
    await state.set_state(ReportPeriod.waiting_for_start)
    await message.answer(
        "📊 **Отчет за период**\n\nВведите **начальную дату** (ДД.ММ.ГГГГ):",
        reply_markup=cancel_keyboard(),
        parse_mode="Markdown",
    )


@router.callback_query(F.data.startswith("report_obj_"))
async def object_report_start(callback: CallbackQuery, state: FSMContext):
    obj_id = int(callback.data.split("_")[2])
    obj = await get_object(obj_id)
    if not obj:
        await callback.answer("Объект не найден", show_alert=True)
        return
    await state.update_data(report_obj_id=obj_id, report_obj_name=obj["name"])
    await state.set_state(ReportPeriod.waiting_for_start)
    await callback.message.edit_text(
        f"📊 Отчет по «{obj['name']}»\n\nВведите **начальную дату** (ДД.ММ.ГГГГ):",
        parse_mode="Markdown",
    )


@router.message(ReportPeriod.waiting_for_start)
async def report_start_date(message: Message, state: FSMContext):
    date = parse_date(message.text)
    if date is None:
        await message.answer("❌ Неверный формат. Используйте ДД.ММ.ГГГГ:")
        return
    await state.update_data(report_start=date.strftime("%Y-%m-%d"))
    await state.set_state(ReportPeriod.waiting_for_end)
    await message.answer("Введите **конечную дату** (ДД.ММ.ГГГГ):", parse_mode="Markdown")


@router.message(ReportPeriod.waiting_for_end)
async def report_end_date(message: Message, state: FSMContext):
    date = parse_date(message.text)
    if date is None:
        await message.answer("❌ Неверный формат. Используйте ДД.ММ.ГГГГ:")
        return
    data = await state.get_data()
    start = data["report_start"]
    end = date.strftime("%Y-%m-%d")
    obj_id = data.get("report_obj_id")
    obj_name = data.get("report_obj_name")
    await state.clear()

    msg = await message.answer("⏳ Генерация отчета...")
    try:
        if obj_id and obj_name:
            filepath = await generate_object_report(obj_id, obj_name, start, end)
            text_report = await generate_object_report_text(obj_id, obj_name, start, end)
            await message.answer(f"📊 **Текстовый отчет**\n\n{text_report}", parse_mode="Markdown")
            caption = f"📊 Отчет «{obj_name}» {format_date(start)} — {format_date(end)}"
        else:
            filepath = await generate_all_objects_report(start, end)
            caption = f"📊 Общий отчет {format_date(start)} — {format_date(end)}"
        doc = FSInputFile(filepath)
        await message.answer_document(doc, caption=caption)
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")
    finally:
        await msg.delete()
        await message.answer("🏢 Главное меню", reply_markup=head_office_menu())


# --- View access codes ---
@router.message(F.text == "🔑 Коды доступа")
async def show_access_codes(message: Message):
    codes = await get_all_codes_with_users()
    if not codes:
        await message.answer("❌ Нет созданных кодов доступа.")
        return

    lines = ["🔑 **Все коды доступа:**\n"]
    for c in codes:
        role_names = {"head_office": "ГО", "manager": "Менеджер", "employee": "Сотрудник"}
        role_label = role_names.get(c["role"], c["role"])
        obj = f" ({c['object_name']})" if c["object_name"] else ""
        names = c["user_names"] if c["user_names"] else "—"
        lines.append(f"• {names} — `{c['code']}` ({role_label}{obj})")

    await message.answer("\n".join(lines), parse_mode="Markdown")


# --- Create HQ code ---
@router.message(F.text == "👤 Создать код ГО")
async def create_hq_code_start(message: Message, state: FSMContext):
    await state.set_state(AddHQUser.waiting_for_name)
    await message.answer(
        "👤 **Создание кода головного офиса**\n\n"
        "Введите **имя** сотрудника ГО:",
        reply_markup=cancel_keyboard(),
        parse_mode="Markdown",
    )


@router.message(AddHQUser.waiting_for_name)
async def create_hq_code_name(message: Message, state: FSMContext):
    name = message.text.strip()
    if len(name) < 2 or len(name) > 100:
        await message.answer("❌ Имя должно быть от 2 до 100 символов. Попробуйте снова:")
        return
    await state.update_data(hq_name=name)
    await state.set_state(AddHQUser.waiting_for_code)
    await message.answer(
        f"Имя: {name}\n\n"
        "Введите **код доступа** для этого сотрудника ГО:",
        reply_markup=back_keyboard(),
        parse_mode="Markdown",
    )


@router.message(AddHQUser.waiting_for_code)
async def create_hq_code_final(message: Message, state: FSMContext):
    code = message.text.strip()
    if await code_exists(code):
        await message.answer("❌ Этот код уже используется. Придумайте другой:")
        return
    if len(code) < 3:
        await message.answer("❌ Код должен быть минимум 3 символа. Попробуйте снова:")
        return
    data = await state.get_data()
    hq_name = data["hq_name"]
    await create_access_code(code, "head_office", None)
    await state.clear()
    await message.answer(
        f"✅ Код головного офиса создан!\n\n"
        f"Имя: {hq_name}\n"
        f"Код: `{code}`\n\n"
        f"Этот код предоставляет полный доступ к управлению.",
        parse_mode="Markdown",
        reply_markup=head_office_menu(),
    )


@router.callback_query(F.data == "cancel_action")
async def cancel_action(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("❌ Действие отменено.")
    await callback.message.answer("🏢 Главное меню", reply_markup=head_office_menu())
