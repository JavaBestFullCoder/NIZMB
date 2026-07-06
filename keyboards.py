from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder
from database import get_objects


def head_office_menu() -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.row(KeyboardButton(text="📋 Управление объектами"))
    builder.row(KeyboardButton(text="📊 Отчеты за период"), KeyboardButton(text="💰 Мой счет"))
    builder.row(KeyboardButton(text="💸 Расход"), KeyboardButton(text="☁️ Google Диск"))
    return builder.as_markup(resize_keyboard=True)


def manager_menu() -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.row(KeyboardButton(text="💰 Приход"), KeyboardButton(text="💸 Расход"))
    builder.row(KeyboardButton(text="🔄 Перевод в офис"), KeyboardButton(text="👥 Сотрудники"))
    builder.row(KeyboardButton(text="📊 Отчеты"), KeyboardButton(text="☁️ Google Диск"))
    return builder.as_markup(resize_keyboard=True)


def employee_menu() -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.row(KeyboardButton(text="💰 Приход"), KeyboardButton(text="💸 Расход"))
    builder.row(KeyboardButton(text="🔄 Перевод в офис"), KeyboardButton(text="📊 Отчеты"))
    builder.row(KeyboardButton(text="☁️ Google Диск"))
    return builder.as_markup(resize_keyboard=True)


def back_keyboard() -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.add(KeyboardButton(text="🔙 Назад"))
    return builder.as_markup(resize_keyboard=True)


def cancel_keyboard() -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.add(KeyboardButton(text="❌ Отмена"))
    return builder.as_markup(resize_keyboard=True)


# --- Inline keyboards ---

async def objects_inline(extra_buttons: list[tuple[str, str]] | None = None) -> InlineKeyboardMarkup:
    objects = await get_objects()
    builder = InlineKeyboardBuilder()
    for obj in objects:
        builder.button(text=f"{obj['name']} ({obj['user_count']} сотр.)", callback_data=f"obj_{obj['id']}")
    builder.adjust(1)
    if extra_buttons:
        for text, cb in extra_buttons:
            builder.button(text=text, callback_data=cb)
    builder.button(text="🔙 Назад", callback_data="back_to_menu")
    builder.adjust(1)
    return builder.as_markup()


async def object_actions_inline(obj_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="📊 Отчет за период", callback_data=f"report_obj_{obj_id}")
    builder.button(text="👥 Сотрудники", callback_data=f"employees_{obj_id}")
    builder.button(text="➕ Добавить сотрудника", callback_data=f"add_emp_{obj_id}")
    builder.button(text="💰 Баланс", callback_data=f"balance_{obj_id}")
    builder.button(text="🗑 Удалить объект", callback_data=f"del_obj_{obj_id}")
    builder.button(text="🔙 Назад", callback_data="back_to_objects")
    builder.adjust(1)
    return builder.as_markup()


def confirm_keyboard(action: str, data: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Подтвердить", callback_data=f"confirm_{action}_{data}")
    builder.button(text="❌ Отмена", callback_data="cancel_action")
    builder.adjust(2)
    return builder.as_markup()


def date_back_keyboard(callback: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 Назад", callback_data=callback)
    return builder.as_markup()
