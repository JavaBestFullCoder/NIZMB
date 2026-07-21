from aiogram.filters import Filter
from aiogram.types import Message, CallbackQuery
from database import get_user_by_telegram


class RoleFilter(Filter):
    def __init__(self, *roles: str):
        self.roles = set(roles)

    async def __call__(self, obj: Message | CallbackQuery) -> bool:
        user = await get_user_by_telegram(obj.from_user.id)
        if user is None:
            return False
        return user["role"] in self.roles


class IsHeadOffice(Filter):
    async def __call__(self, obj: Message | CallbackQuery) -> bool:
        user = await get_user_by_telegram(obj.from_user.id)
        return user is not None and user["role"] == "head_office"


class IsObjectUser(Filter):
    async def __call__(self, obj: Message | CallbackQuery) -> bool:
        user = await get_user_by_telegram(obj.from_user.id)
        if user is None:
            return False
        if user["role"] in ("manager", "employee"):
            return True
        if user["role"] == "head_office":
            from hq_connected import hq_connected
            return obj.from_user.id in hq_connected
        return False



