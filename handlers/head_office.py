import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, FSInputFile
from aiogram.fsm.context import FSMContext

logger = logging.getLogger(__name__)

from filters import IsHeadOffice
from hq_connected import hq_connected
from keyboards import (
    head_office_menu, objects_inline, object_actions_inline,
    confirm_keyboard, cancel_keyboard, back_keyboard,
    access_management_kb, delete_object_inline,
    confirm_delete_txn_kb, hq_users_inline,
    connected_manager_menu,
)
from database import (
    get_object, get_objects, create_object, delete_object,
    create_transaction, get_object_balance, get_employees,
    code_exists, get_user_by_telegram, create_access_code,
    get_all_codes_with_users, get_transaction_by_id,
    delete_transaction, get_transfer_link_by_transaction,
    get_hq_users, delete_user, save_deleted_operation,
)
from states import AddObject, AddEmployee, AddExpense, AddHQUser, ReportPeriod, DeleteOperation, DeleteHQUser
from services.balance import get_hq_balance_text
from services.reports import generate_all_objects_report, generate_object_report, generate_object_report_text
from utils import parse_amount, parse_date, format_amount, format_date, format_datetime, today_str, now_str, date_to_dt

router = Router()
router.message.filter(IsHeadOffice())
router.callback_query.filter(IsHeadOffice())


@router.message(F.text == "🔙 Назад")
async def back_to_menu(message: Message, state: FSMContext):
    await state.clear()
    if message.from_user.id in hq_connected:
        await message.answer("🏢 Меню объекта", reply_markup=connected_manager_menu())
    else:
        await message.answer("🏢 Главное меню", reply_markup=head_office_menu())


@router.message(F.text == "❌ Отмена")
async def cancel_hq(message: Message, state: FSMContext):
    await state.clear()
    if message.from_user.id in hq_connected:
        await message.answer("❌ Отменено", reply_markup=connected_manager_menu())
    else:
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
    await state.update_data(obj_code=code)
    await state.set_state(AddObject.waiting_for_manager_name)
    await message.answer(
        "Введите **имя менеджера** (или отправьте 0, чтобы использовать ник в Telegram):",
        reply_markup=back_keyboard(),
        parse_mode="Markdown",
    )


@router.message(AddObject.waiting_for_manager_name)
async def add_object_manager_name(message: Message, state: FSMContext):
    name_input = message.text.strip()
    data = await state.get_data()
    obj_name = data["obj_name"]
    code = data["obj_code"]
    manager_name = None if name_input == "0" else (name_input if len(name_input) >= 2 else None)
    obj_id = await create_object(obj_name)
    await create_access_code(code, "manager", obj_id, default_name=manager_name)
    await state.clear()
    await message.answer(
        f"✅ Объект «{obj_name}» создан!\n"
        f"Код менеджера: `{code}`\n"
        f"Имя менеджера: {manager_name or 'будет использован ник Telegram'}\n\n"
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


@router.callback_query(F.data.startswith("connect_obj_"))
async def connect_to_object(callback: CallbackQuery):
    obj_id = int(callback.data.split("_")[2])
    obj = await get_object(obj_id)
    if not obj:
        await callback.answer("Объект не найден", show_alert=True)
        return
    hq_connected[callback.from_user.id] = {"object_id": obj_id, "object_name": obj["name"]}
    await callback.message.edit_text(
        f"🔗 Подключение к «{obj['name']}»\n\n"
        f"Вы вошли в интерфейс объекта. Все операции будут записаны от вашего имени (ГО).",
    )
    await callback.message.answer(
        f"🏢 Меню «{obj['name']}»",
        reply_markup=connected_manager_menu(),
    )


@router.message(F.text == "🔙 Выйти из объекта")
async def disconnect_from_object(message: Message, state: FSMContext):
    await state.clear()
    info = hq_connected.pop(message.from_user.id, None)
    if info:
        await message.answer(
            f"✅ Вы вышли из интерфейса «{info['object_name']}».",
            reply_markup=head_office_menu(),
        )
    else:
        await message.answer("🏢 Главное меню", reply_markup=head_office_menu())


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
    await state.update_data(emp_code=code)
    await state.set_state(AddEmployee.waiting_for_emp_name)
    await message.answer(
        "Введите **имя сотрудника** (или отправьте 0, чтобы использовать ник в Telegram):",
        reply_markup=back_keyboard(),
        parse_mode="Markdown",
    )


@router.message(AddEmployee.waiting_for_emp_name)
async def add_employee_name(message: Message, state: FSMContext):
    name_input = message.text.strip()
    data = await state.get_data()
    code = data["emp_code"]
    manager_name = None if name_input == "0" else (name_input if len(name_input) >= 2 else None)
    await create_access_code(code, "manager", data["emp_obj_id"], default_name=manager_name)
    await state.clear()
    await message.answer(
        f"✅ Код менеджера создан для «{data['emp_obj_name']}»\n"
        f"Код: `{code}`\n"
        f"Имя: {manager_name or 'будет использован ник Telegram'}\n\n"
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
        f"• Коды доступа\n\n"
        f"Транзакции и история сохранятся. Объект будет скрыт из меню,\n"
        f"но отчёты за период его работы останутся доступны.\n"
        f"Это действие **необратимо**.",
        parse_mode="Markdown",
        reply_markup=confirm_keyboard("delete_object", str(obj_id)),
    )


@router.callback_query(F.data.startswith("confirm_delete_object_"))
async def delete_object_execute(callback: CallbackQuery, state: FSMContext):
    obj_id = int(callback.data.split("_")[3])
    obj = await get_object(obj_id)
    if obj:
        try:
            await delete_object(obj_id)
            await callback.message.edit_text(f"✅ Объект «{obj['name']}» удален.")
        except Exception as e:
            await callback.message.edit_text(f"❌ Ошибка при удалении объекта: {e}")
            logger.exception("Ошибка удаления объекта")
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


_CONNECTED_EXPENSE_LABELS = {
    "expense": ("💸 Расход", "✅ Расход"),
    "director_expense": ("👔 Расход Директора", "✅ Расход Директора"),
    "supplier_payment": ("📦 Оплата поставщика", "✅ Оплата поставщика"),
}


async def _hq_expense_start(message: Message, state: FSMContext, exp_type: str):
    await state.update_data(exp_type=exp_type)
    await state.set_state(AddExpense.waiting_for_amount)
    if message.from_user.id in hq_connected:
        label, _ = _CONNECTED_EXPENSE_LABELS.get(exp_type, ("Расход", "Расход"))
        await message.answer(
            f"{label} объекта\n\nВведите **сумму**:",
            reply_markup=cancel_keyboard(),
            parse_mode="Markdown",
        )
    else:
        label, _ = _HQ_EXPENSE_LABELS.get(exp_type, ("Расход", "Расход"))
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
    date_str = date_to_dt(date)
    exp_type = data.get("exp_type", "expense")

    connected = message.from_user.id in hq_connected
    obj_id = None
    if connected:
        info = hq_connected.get(message.from_user.id)
        if info:
            obj_id = info["object_id"]

    txn_id = await create_transaction(
        object_id=obj_id,
        user_id=user["id"],
        type_=exp_type,
        amount=data["exp_amount"],
        reason=data["exp_reason"],
        date_str=date_str,
    )
    await state.clear()
    if connected:
        _, label_done = _CONNECTED_EXPENSE_LABELS.get(exp_type, ("", "✅ Расход"))
        await message.answer(
            f"{label_done} за {format_datetime(date_str)}:\n"
            f"Сумма: {format_amount(data['exp_amount'])} сум\n"
            f"Причина: {data['exp_reason']}\n"
            f"🆔 ID: {txn_id}",
            reply_markup=connected_manager_menu(),
        )
    else:
        _, label_done = _HQ_EXPENSE_LABELS.get(exp_type, ("", "✅ Расход ГО"))
        await message.answer(
            f"{label_done} за {format_datetime(date_str)}:\n"
            f"Сумма: {format_amount(data['exp_amount'])} сум\n"
            f"Причина: {data['exp_reason']}\n"
            f"🆔 ID: {txn_id}",
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
        menu = connected_manager_menu() if message.from_user.id in hq_connected else head_office_menu()
        await message.answer("🏢 Главное меню", reply_markup=menu)


# --- Access management ---
@router.message(F.text == "🔐 Управление доступом")
async def access_management(message: Message):
    await message.answer(
        "🔐 **Управление доступом**\n\nВыберите действие:",
        reply_markup=access_management_kb(),
        parse_mode="Markdown",
    )


@router.callback_query(F.data == "view_codes")
async def show_access_codes(callback: CallbackQuery):
    codes = await get_all_codes_with_users()
    if not codes:
        await callback.message.edit_text("❌ Нет созданных кодов доступа.", reply_markup=access_management_kb())
        return

    lines = ["🔑 **Все коды доступа:**\n"]
    for c in codes:
        role_names = {"head_office": "ГО", "manager": "Менеджер", "employee": "Сотрудник"}
        role_label = role_names.get(c["role"], c["role"])
        obj = f" ({c['object_name']})" if c["object_name"] else ""
        names = c["user_names"] if c["user_names"] else "—"
        lines.append(f"• {names} — `{c['code']}` ({role_label}{obj})")

    await callback.message.edit_text("\n".join(lines), reply_markup=access_management_kb(), parse_mode="Markdown")


@router.callback_query(F.data == "create_code")
async def create_code_start(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "👤 **Создание кода доступа**\n\n"
        "Введите **имя** сотрудника:",
        parse_mode="Markdown",
    )
    await state.set_state(AddHQUser.waiting_for_name)


@router.message(AddHQUser.waiting_for_name)
async def create_code_name(message: Message, state: FSMContext):
    name = message.text.strip()
    if len(name) < 2 or len(name) > 100:
        await message.answer("❌ Имя должно быть от 2 до 100 символов. Попробуйте снова:")
        return
    await state.update_data(hq_name=name)
    await state.set_state(AddHQUser.waiting_for_code)
    await message.answer(
        f"Имя: {name}\n\n"
        "Введите **код доступа** для этого сотрудника:",
        reply_markup=back_keyboard(),
        parse_mode="Markdown",
    )


@router.message(AddHQUser.waiting_for_code)
async def create_code_final(message: Message, state: FSMContext):
    code = message.text.strip()
    if await code_exists(code):
        await message.answer("❌ Этот код уже используется. Придумайте другой:")
        return
    if len(code) < 3:
        await message.answer("❌ Код должен быть минимум 3 символа. Попробуйте снова:")
        return
    data = await state.get_data()
    hq_name = data["hq_name"]
    await create_access_code(code, "head_office", None, default_name=hq_name)
    await state.clear()
    await message.answer(
        f"✅ Код доступа создан!\n\n"
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
    menu = connected_manager_menu() if callback.from_user.id in hq_connected else head_office_menu()
    await callback.message.answer("🏢 Главное меню", reply_markup=menu)


# --- Delete operation ---

@router.message(F.text == "🗑 Удалить операцию")
async def delete_operation_start(message: Message, state: FSMContext):
    await state.set_state(DeleteOperation.waiting_for_id)
    await message.answer(
        "🗑 **Удаление операции**\n\n"
        "Введите **ID операции** для удаления:",
        reply_markup=cancel_keyboard(),
        parse_mode="Markdown",
    )


@router.message(DeleteOperation.waiting_for_id)
async def delete_operation_id(message: Message, state: FSMContext):
    try:
        txn_id = int(message.text.strip())
    except ValueError:
        await message.answer("❌ ID должен быть числом. Попробуйте снова:")
        return

    txn = await get_transaction_by_id(txn_id)
    if not txn:
        await message.answer("❌ Операция с таким ID не найдена. Попробуйте снова:")
        return

    await state.update_data(delop_txn_id=txn_id, delop_txn=txn)

    type_names = {
        "income": "Приход", "expense": "Расход",
        "director_expense": "Расход Директора",
        "supplier_payment": "Оплата поставщика",
        "transfer_out": "Перевод в офис", "transfer_in": "Перевод из объекта",
    }
    txn_type = type_names.get(txn["type"], txn["type"])
    if txn["object_id"]:
        obj = await get_object(txn["object_id"])
        obj_name = obj["name"] if obj else "Удалённый объект"
    else:
        obj_name = "Головной офис"

    await message.answer(
        f"🔍 **Найдена операция:**\n\n"
        f"🆔 ID: {txn['id']}\n"
        f"📅 Дата: {format_datetime(txn['transaction_date'])}\n"
        f"🏢 Объект: {obj_name}\n"
        f"📋 Тип: {txn_type}\n"
        f"💰 Сумма: {format_amount(txn['amount'])} сум\n"
        f"📝 Причина: {txn.get('reason', '—')}\n\n"
        f"Удалить эту операцию?",
        reply_markup=confirm_delete_txn_kb(txn_id),
        parse_mode="Markdown",
    )


@router.callback_query(F.data.startswith("confirm_del_txn_"))
async def delete_operation_reason_start(callback: CallbackQuery, state: FSMContext):
    current_state = await state.get_state()
    if current_state not in (None, DeleteOperation.waiting_for_id.state):
        await callback.answer("⚠️ Сначала завершите текущее действие", show_alert=True)
        return
    txn_id = int(callback.data.split("_")[3])
    txn = await get_transaction_by_id(txn_id)
    if not txn:
        await callback.message.edit_text("❌ Операция уже удалена или не найдена.")
        await state.clear()
        return
    await state.update_data(delop_confirm_txn_id=txn_id, delop_confirm_txn=txn)
    await state.set_state(DeleteOperation.waiting_for_reason)
    await callback.message.edit_text(
        "🗑 **Подтверждение удаления**\n\n"
        "Введите **причину удаления**:",
        parse_mode="Markdown",
    )


@router.message(DeleteOperation.waiting_for_reason, IsHeadOffice())
async def delete_operation_execute(message: Message, state: FSMContext):
    delete_reason = message.text.strip()
    if len(delete_reason) < 2:
        await message.answer("❌ Причина должна быть минимум 2 символа. Введите снова:")
        return

    data = await state.get_data()
    txn_id = data["delop_confirm_txn_id"]
    txn = data["delop_confirm_txn"]

    try:
        user = await get_user_by_telegram(message.from_user.id)
        deleted_by_user_id = user["id"]
        deleted_by_name = user.get("name", "")

        # Save deleted operation record for the primary transaction
        await save_deleted_operation(txn, deleted_by_user_id, deleted_by_name, delete_reason)

        # Cascade delete linked transfers
        link = await get_transfer_link_by_transaction(txn_id)
        if link:
            other_id = link["transfer_in_id"] if link["transfer_out_id"] == txn_id else link["transfer_out_id"]
            # Save the other side too (fetch it first)
            other_txn = await get_transaction_by_id(other_id)
            if other_txn:
                await save_deleted_operation(other_txn, deleted_by_user_id, deleted_by_name, delete_reason)
            # delete_transaction now auto-cleans transfer_links
            await delete_transaction(other_id)
            await delete_transaction(txn_id)
            await message.answer(
                f"✅ Операция ID {txn_id} и связанный перевод удалены.\n"
                f"Причина: {delete_reason}"
            )
        else:
            await delete_transaction(txn_id)
            await message.answer(
                f"✅ Операция ID {txn_id} удалена.\n"
                f"Причина: {delete_reason}"
            )
    except Exception as e:
        logger.exception("Ошибка удаления операции")
        await message.answer(f"❌ Ошибка при удалении: {e}")

    await state.clear()
    menu = connected_manager_menu() if message.from_user.id in hq_connected else head_office_menu()
    await message.answer("🏢 Главное меню", reply_markup=menu)


# --- Delete HQ user ---

@router.message(F.text == "👤 Удалить сотрудника ГО")
async def delete_hq_user_start(message: Message):
    kb = await hq_users_inline()
    await message.answer(
        "👤 **Удаление сотрудника ГО**\n\nВыберите сотрудника для удаления:",
        reply_markup=kb,
        parse_mode="Markdown",
    )


@router.callback_query(F.data.startswith("del_hq_user_"))
async def delete_hq_user_execute(callback: CallbackQuery):
    user_id = int(callback.data.split("_")[3])
    caller = await get_user_by_telegram(callback.from_user.id)
    if caller and caller["id"] == user_id:
        await callback.answer("❌ Нельзя удалить самого себя!", show_alert=True)
        return
    await delete_user(user_id)
    await callback.message.edit_text("✅ Сотрудник ГО удалён.")
    await callback.message.answer("🏢 Главное меню", reply_markup=head_office_menu())
