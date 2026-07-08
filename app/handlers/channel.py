from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from app.bot import get_context
from app.config import get_settings

router = Router()


def allowed(message: Message) -> bool:
    return get_settings().is_admin(message.from_user.id if message.from_user else None)


@router.message(Command("channel_bind"))
async def bind(message: Message) -> None:
    if not allowed(message):
        return
    channel_id = message.text.partition(" ")[2].strip()
    await get_context().channel.update(channel_id=channel_id)
    await message.answer("Канал привязан." if channel_id else "Укажите channel_id.")


@router.message(Command("channel_enable"))
async def enable(message: Message) -> None:
    if not allowed(message):
        return
    await get_context().channel.update(enabled=1)
    await message.answer("Постинг включен.")


@router.message(Command("channel_disable"))
async def disable(message: Message) -> None:
    if not allowed(message):
        return
    await get_context().channel.update(enabled=0)
    await message.answer("Постинг выключен.")


@router.message(Command("channel_status"))
async def status(message: Message) -> None:
    if not allowed(message):
        return
    s = await get_context().channel.settings()
    await message.answer(str(dict(s)) if s else "Нет настроек")


@router.message(Command("channel_test", "channel_post_now"))
async def post_now(message: Message) -> None:
    if not allowed(message):
        return
    await message.answer(await get_context().channel.post_now(message.bot))
