from aiogram import Router, F
from aiogram.types import Message
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext

from config import HEAD_OFFICE_CODE
from database import resolve_code, get_user_by_telegram, login_user, update_user_name
from states import Registration
from keyboards import head_office_menu, manager_menu, employee_menu
from utils import today_str

router = Router()


@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    user = await get_user_by_telegram(message.from_user.id)
    if user:
        await show_menu(message, user)
        return
    await state.set_state(Registration.waiting_for_code)
    await message.answer(
        "👋 Добро пожаловать!\n\nВведите ваш код доступа:"
    )


@router.message(Registration.waiting_for_code)
async def process_code(message: Message, state: FSMContext):
    code = message.text.strip()
    await state.clear()
    tid = message.from_user.id
    username = message.from_user.username
    first_name = message.from_user.first_name or "User"

    # Head office: always allowed, unlimited users
    if code == HEAD_OFFICE_CODE:
        user = await get_user_by_telegram(tid)
        if user:
            from database import get_db
            db = await get_db()
            await db.execute(
                "UPDATE users SET role = 'head_office', access_code = ?, object_id = NULL WHERE telegram_id = ?",
                (code, tid),
            )
            await db.commit()
        else:
            from database import get_db
            db = await get_db()
            await db.execute(
                "INSERT INTO users (telegram_id, telegram_username, name, role, access_code) VALUES (?, ?, ?, ?, ?)",
                (tid, username, first_name, "head_office", code),
            )
            await db.commit()
        user = await get_user_by_telegram(tid)
        await message.answer(
            "✅ Вы авторизованы как **Головной офис**\n\n"
            "У вас полный доступ к управлению объектами и отчетности.",
            parse_mode="Markdown",
        )
        await show_menu(message, user)
        return

    # Other codes — resolve from access_codes table
    ac = await resolve_code(code)
    if not ac:
        await message.answer("❌ Неверный код доступа. Попробуйте снова.\n\nВведите /start для новой попытки.")
        return

    user = await login_user(tid, username, code, first_name)
    if not user:
        await message.answer("❌ Ошибка входа. Попробуйте снова.")
        return

    # Update name if not set
    if not user["name"]:
        await update_user_name(tid, first_name)
        user["name"] = first_name

    await message.answer(
        f"✅ Вы вошли как **{user['role']}**\n"
        f"Имя: {user['name']}",
        parse_mode="Markdown",
    )
    await show_menu(message, user)


async def show_menu(message: Message, user: dict):
    role = user["role"]
    if role == "head_office":
        await message.answer("🏢 **Главное меню**", parse_mode="Markdown", reply_markup=head_office_menu())
    elif role == "manager":
        from database import get_object
        obj_name = ""
        if user["object_id"]:
            obj = await get_object(user["object_id"])
            if obj:
                obj_name = f" ({obj['name']})"
        await message.answer(
            f"👤 Менеджер{obj_name}\n🏢 **Главное меню**",
            parse_mode="Markdown",
            reply_markup=manager_menu(),
        )
    elif role == "employee":
        from database import get_object
        obj_name = ""
        if user["object_id"]:
            obj = await get_object(user["object_id"])
            if obj:
                obj_name = f" ({obj['name']})"
        await message.answer(
            f"👤 Сотрудник{obj_name}\n🏢 **Главное меню**",
            parse_mode="Markdown",
            reply_markup=employee_menu(),
        )
