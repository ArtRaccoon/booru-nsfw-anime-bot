from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from app.group_posting import POST_ERROR, publish_group_post
from app.safety import is_admin

router = Router()


def _arg(message: Message) -> str:
    return message.text.split(maxsplit=1)[1].strip() if len(message.text.split()) > 1 else ""


async def require_admin(message: Message, settings) -> bool:
    if not is_admin(message.from_user.id, settings.admin_ids):
        await message.answer("Admin only.")
        return False
    return True


def _settings_text(row) -> str:
    return (
        "🛰 Групповой постинг\n"
        f"Чат: {row['target_chat_id'] or 'не задан'}\n"
        f"Статус: {'включен' if row['enabled'] else 'выключен'}\n"
        f"Режим: {row['mode']}\n"
        f"Источник: {row['provider'] or 'auto'}\n"
        f"Теги: {row['tags'] or '-'}\n"
        f"Интервал: {row['interval_minutes']} мин\n"
        f"Последний пост: {row['last_posted_at'] or '-'}"
    )


@router.message(Command("group_bind"))
async def group_bind(message: Message, db, settings) -> None:
    if not await require_admin(message, settings):
        return
    try:
        chat_id = int(_arg(message))
    except ValueError:
        await message.answer("Использование: /group_bind <chat_id>")
        return
    await db.update_group_posting_settings(target_chat_id=chat_id)
    await message.answer(f"Группа привязана: {chat_id}")


@router.message(Command("group_enable"))
async def group_enable(message: Message, db, settings) -> None:
    if await require_admin(message, settings):
        await db.update_group_posting_settings(enabled=1)
        await message.answer("Групповой постинг включен.")


@router.message(Command("group_disable"))
async def group_disable(message: Message, db, settings) -> None:
    if await require_admin(message, settings):
        await db.update_group_posting_settings(enabled=0)
        await message.answer("Групповой постинг выключен.")


@router.message(Command("group_status"))
async def group_status(message: Message, db, settings) -> None:
    if await require_admin(message, settings):
        await message.answer(_settings_text(await db.get_group_posting_settings()))


@router.message(Command("group_mode"))
async def group_mode(message: Message, db, settings) -> None:
    if not await require_admin(message, settings):
        return
    mode = _arg(message).lower()
    if mode not in {"sfw", "nsfw", "mixed"}:
        await message.answer("Использование: /group_mode sfw|nsfw|mixed")
        return
    await db.update_group_posting_settings(mode=mode)
    await message.answer(f"Режим: {mode}")


@router.message(Command("group_tags"))
async def group_tags(message: Message, db, settings) -> None:
    if await require_admin(message, settings):
        await db.update_group_posting_settings(tags=_arg(message))
        await message.answer("Теги обновлены.")


@router.message(Command("group_provider"))
async def group_provider(message: Message, db, settings, providers_map) -> None:
    if not await require_admin(message, settings):
        return
    provider = _arg(message) or "auto"
    if provider != "auto" and provider not in providers_map:
        await message.answer("Unknown provider.")
        return
    await db.update_group_posting_settings(provider=provider)
    await message.answer(f"Источник: {provider}")


@router.message(Command("group_interval"))
async def group_interval(message: Message, db, settings) -> None:
    if not await require_admin(message, settings):
        return
    try:
        minutes = int(_arg(message))
    except ValueError:
        await message.answer("Использование: /group_interval <minutes>")
        return
    await db.update_group_posting_settings(interval_minutes=minutes)
    row = await db.get_group_posting_settings()
    await message.answer(f"Интервал: {row['interval_minutes']} мин")


@router.message(Command("group_post_now"))
async def group_post_now(message: Message, db, settings, providers_map) -> None:
    if not await require_admin(message, settings):
        return
    ok = await publish_group_post(
        message.bot, db, providers_map, dict(await db.get_group_posting_settings())
    )
    await message.answer("Опубликовано." if ok else POST_ERROR)


@router.message(Command("group_history"))
async def group_history(message: Message, db, settings) -> None:
    if not await require_admin(message, settings):
        return
    rows = await db.group_history(10)
    text = "📜 История\n" + "\n".join(
        f"{r['posted_at']} {r['provider']}#{r['post_id']}" for r in rows
    )
    await message.answer(text if rows else "История пуста.")


@router.message(Command("group_reset_history"))
async def group_reset_history(message: Message, db, settings) -> None:
    if not await require_admin(message, settings):
        return
    row = await db.get_group_posting_settings()
    if not row["target_chat_id"]:
        await message.answer("Чат не задан.")
        return
    await db.clear_group_history(row["target_chat_id"])
    await message.answer("История очищена.")
