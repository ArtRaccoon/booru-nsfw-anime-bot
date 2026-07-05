from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from app.safety import is_admin

router = Router()


async def require_admin(message: Message, settings) -> bool:
    if not is_admin(message.from_user.id, settings.admin_ids):
        await message.answer("Admin only.")
        return False
    return True


@router.message(Command("admin"))
async def admin(message: Message, settings) -> None:
    if await require_admin(message, settings):
        await message.answer(
            "Admin commands: /stats, /broadcast <text>, /reload_providers, "
            "/set_global_provider <provider>"
        )


@router.message(Command("stats"))
async def stats(message: Message, db, settings) -> None:
    if not await require_admin(message, settings):
        return
    data = await db.get_stats()
    await message.answer(
        f"Users: {data['users']}\nFavorites: {data['favorites']}\nSearches: {data['searches']}"
    )


@router.message(Command("broadcast"))
async def broadcast(message: Message, settings) -> None:
    if await require_admin(message, settings):
        await message.answer("Broadcast accepted (delivery queue placeholder).")


@router.message(Command("reload_providers"))
async def reload_providers(message: Message, settings) -> None:
    if await require_admin(message, settings):
        await message.answer(
            "Provider config reload requested. Restart container to apply env changes."
        )


@router.message(Command("set_global_provider"))
async def set_global_provider(message: Message, db, settings, providers_map) -> None:
    if not await require_admin(message, settings):
        return
    provider = message.text.split(maxsplit=1)[1].strip() if len(message.text.split()) > 1 else ""
    if provider not in providers_map:
        await message.answer("Unknown provider.")
        return
    await db.conn.execute(
        "INSERT INTO settings(key, value) VALUES('default_provider', ?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (provider,),
    )
    await db.conn.commit()
    settings.default_provider = provider
    await message.answer(f"Global default provider set to {provider}.")
