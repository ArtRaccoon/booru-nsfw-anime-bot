from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from app.channel_posting import (
    POST_ERROR,
    positive_id_warning,
    publish_channel_post,
    resolve_channel_target,
    test_channel,
)
from app.keyboards import channel_mode_keyboard, channel_posting_keyboard, channel_provider_keyboard
from app.safety import is_admin

router = Router()
DEPRECATION = "Команда работает, но теперь лучше использовать /channel_*"


class ChannelPostingFSM(StatesGroup):
    bind = State()
    tags = State()
    interval = State()


def _arg(message: Message) -> str:
    return (
        message.text.split(maxsplit=1)[1].strip()
        if message.text and len(message.text.split()) > 1
        else ""
    )


async def require_admin(message: Message, settings) -> bool:
    if not is_admin(message.from_user.id, settings.admin_ids):
        await message.answer("Admin only.")
        return False
    return True


def _is_group_alias(message: Message) -> bool:
    return bool(message.text and message.text.split()[0].split("@")[0].startswith("/group_"))


async def _maybe_deprecated(message: Message) -> None:
    if _is_group_alias(message):
        await message.answer(DEPRECATION)


async def channel_status_text(db, row=None) -> str:
    row = row or await db.get_group_posting_settings()
    stats = await db.group_history_stats(
        row["target_chat_id"] if row and row["target_chat_id"] else None
    )
    last_ids = ", ".join(str(r["post_id"]) for r in stats["rows"][:10]) or "-"
    return (
        "📢 Постинг в канал\n\n"
        f"Статус: {'включён' if row['enabled'] else 'выключен'}\n"
        f"Канал: {row['target_chat_id'] or 'не задан'}\n"
        f"Режим: {str(row['mode']).upper()}\n"
        f"Источник: {row['provider'] or 'auto'}\n"
        f"Теги: {row['tags'] or '-'}\n"
        f"Интервал: {row['interval_minutes']} мин\n"
        f"Последний пост: {row['last_posted_at'] or stats['last'] or '-'}\n"
        f"История: {stats['total']} постов\n"
        f"Последние ID: {last_ids}"
    )


async def refresh(message, db) -> None:
    await message.edit_text(await channel_status_text(db), reply_markup=channel_posting_keyboard())


@router.message(Command("channel_bind", "group_bind"))
async def channel_bind(message: Message, db, settings) -> None:
    if not await require_admin(message, settings):
        return
    await _maybe_deprecated(message)
    try:
        target = resolve_channel_target(_arg(message) or message)
    except ValueError:
        await message.answer("Использование: /channel_bind <channel_id_or_username>")
        return
    await db.update_group_posting_settings(target_chat_id=target)
    warn = positive_id_warning(target)
    await message.answer((warn + "\n" if warn else "") + f"Канал привязан: {target}")


@router.message(Command("channel_enable", "group_enable"))
async def channel_enable(message: Message, db, settings) -> None:
    if await require_admin(message, settings):
        await _maybe_deprecated(message)
        await db.update_group_posting_settings(enabled=1)
        await message.answer("Постинг в канал включён.")


@router.message(Command("channel_disable", "group_disable"))
async def channel_disable(message: Message, db, settings) -> None:
    if await require_admin(message, settings):
        await _maybe_deprecated(message)
        await db.update_group_posting_settings(enabled=0)
        await message.answer("Постинг в канал выключен.")


@router.message(Command("channel_status", "group_status"))
async def channel_status(message: Message, db, settings) -> None:
    if await require_admin(message, settings):
        await _maybe_deprecated(message)
        await message.answer(await channel_status_text(db))


@router.message(Command("channel_mode", "group_mode"))
async def channel_mode(message: Message, db, settings) -> None:
    if not await require_admin(message, settings):
        return
    await _maybe_deprecated(message)
    mode = _arg(message).lower()
    if mode not in {"sfw", "nsfw", "mixed"}:
        await message.answer("Использование: /channel_mode sfw|nsfw|mixed")
        return
    await db.update_group_posting_settings(mode=mode)
    await message.answer(f"Режим: {mode.upper()}")


@router.message(Command("channel_tags", "group_tags"))
async def channel_tags(message: Message, db, settings) -> None:
    if await require_admin(message, settings):
        await _maybe_deprecated(message)
        await db.update_group_posting_settings(tags=_arg(message))
        await message.answer("Теги обновлены.")


@router.message(Command("channel_provider", "group_provider"))
async def channel_provider(message: Message, db, settings, providers_map) -> None:
    if not await require_admin(message, settings):
        return
    await _maybe_deprecated(message)
    provider = _arg(message) or "auto"
    if provider != "auto" and provider not in providers_map:
        await message.answer("Unknown provider.")
        return
    await db.update_group_posting_settings(provider=provider)
    await message.answer(f"Источник: {provider}")


@router.message(Command("channel_interval", "group_interval"))
async def channel_interval(message: Message, db, settings) -> None:
    if not await require_admin(message, settings):
        return
    await _maybe_deprecated(message)
    try:
        minutes = int(_arg(message))
    except ValueError:
        await message.answer("Использование: /channel_interval <minutes>")
        return
    await db.update_group_posting_settings(interval_minutes=minutes)
    row = await db.get_group_posting_settings()
    await message.answer(f"Интервал: {row['interval_minutes']} мин")


@router.message(Command("channel_post_now", "group_post_now"))
async def channel_post_now(message: Message, db, settings, providers_map) -> None:
    if not await require_admin(message, settings):
        return
    await _maybe_deprecated(message)
    row = dict(await db.get_group_posting_settings())
    ok, err = await publish_channel_post(message.bot, db, providers_map, row)
    await message.answer(
        "Опубликовано."
        if ok
        else (
            "❌ Не удалось опубликовать\n\n"
            f"Канал: {row.get('target_chat_id') or '-'}\n{err or POST_ERROR}"
        )
    )


@router.message(Command("channel_test"))
async def channel_test_cmd(message: Message, db, settings) -> None:
    if not await require_admin(message, settings):
        return
    row = await db.get_group_posting_settings()
    target = row["target_chat_id"]
    if not target:
        await message.answer("Канал не задан.")
        return
    ok, text = await test_channel(message.bot, target)
    await message.answer(("✅ " if ok else "❌ ") + text)


@router.message(Command("channel_history", "group_history"))
async def channel_history(message: Message, db, settings) -> None:
    if not await require_admin(message, settings):
        return
    await _maybe_deprecated(message)
    rows = await db.group_history(10)
    text = "📜 История\n" + "\n".join(
        f"{r['posted_at']} {r['provider']}#{r['post_id']}" for r in rows
    )
    await message.answer(text if rows else "История пуста.")


@router.message(Command("channel_reset_history", "group_reset_history"))
async def channel_reset_history(message: Message, db, settings) -> None:
    if not await require_admin(message, settings):
        return
    await _maybe_deprecated(message)
    row = await db.get_group_posting_settings()
    target = row["target_chat_id"]
    if not target:
        await message.answer("Канал не задан.")
        return
    await db.clear_group_history(target)
    await message.answer("История очищена.")


@router.callback_query(F.data == "admin_channel_posting")
async def admin_channel_posting(callback: CallbackQuery, db, settings) -> None:
    if not is_admin(callback.from_user.id, settings.admin_ids):
        await callback.answer("Только для админа.", show_alert=True)
        return
    await refresh(callback.message, db)
    await callback.answer()


@router.callback_query(
    F.data.in_(
        {
            "channel_enable",
            "channel_disable",
            "channel_post_now",
            "channel_test",
            "channel_history",
            "channel_reset_history",
            "channel_bind",
            "channel_tags",
            "channel_interval",
            "channel_mode",
        }
    )
)
async def channel_buttons(
    callback: CallbackQuery, db, settings, providers_map, state: FSMContext
) -> None:
    if not is_admin(callback.from_user.id, settings.admin_ids):
        await callback.answer("Только для админа.", show_alert=True)
        return
    data = callback.data
    if data == "channel_enable":
        await db.update_group_posting_settings(enabled=1)
        await refresh(callback.message, db)
    elif data == "channel_disable":
        await db.update_group_posting_settings(enabled=0)
        await refresh(callback.message, db)
    elif data == "channel_mode":
        await callback.message.edit_text("Выбери режим:", reply_markup=channel_mode_keyboard())
    elif data == "channel_bind":
        await state.set_state(ChannelPostingFSM.bind)
        await callback.message.answer(
            "Отправь ID канала, @username канала или перешли сообщение из канала."
        )
    elif data == "channel_tags":
        await state.set_state(ChannelPostingFSM.tags)
        await callback.message.answer("Отправь теги для автопостинга.")
    elif data == "channel_interval":
        await state.set_state(ChannelPostingFSM.interval)
        await callback.message.answer("Отправь интервал в минутах. Минимум 15.")
    elif data == "channel_post_now":
        row = dict(await db.get_group_posting_settings())
        ok, err = await publish_channel_post(callback.bot, db, providers_map, row)
        await callback.message.answer(
            "Опубликовано."
            if ok
            else (
                "❌ Не удалось опубликовать\n\n"
                f"Канал: {row.get('target_chat_id') or '-'}\n{err or POST_ERROR}"
            )
        )
    elif data == "channel_test":
        row = await db.get_group_posting_settings()
        ok, text = await test_channel(callback.bot, row["target_chat_id"])
        await callback.message.answer(("✅ " if ok else "❌ ") + text)
    elif data == "channel_history":
        await channel_history(callback.message, db, settings)
    elif data == "channel_reset_history":
        row = await db.get_group_posting_settings()
        await db.clear_group_history(row["target_chat_id"])
        await refresh(callback.message, db)
    await callback.answer()


@router.callback_query(F.data.startswith("channel_set_mode:"))
async def set_mode(callback: CallbackQuery, db, settings) -> None:
    if not is_admin(callback.from_user.id, settings.admin_ids):
        return
    await db.update_group_posting_settings(mode=callback.data.split(":", 1)[1])
    await refresh(callback.message, db)
    await callback.answer()


@router.callback_query(F.data.startswith("channel_provider:"))
async def provider_picker(callback: CallbackQuery, providers_map, settings) -> None:
    if not is_admin(callback.from_user.id, settings.admin_ids):
        return
    page = int(callback.data.split(":", 1)[1])
    await callback.message.edit_text(
        "Выбери источник:", reply_markup=channel_provider_keyboard(list(providers_map), page)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("channel_set_provider:"))
async def set_provider(callback: CallbackQuery, db, settings) -> None:
    if not is_admin(callback.from_user.id, settings.admin_ids):
        return
    await db.update_group_posting_settings(provider=callback.data.split(":", 1)[1])
    await refresh(callback.message, db)
    await callback.answer()


@router.message(ChannelPostingFSM.bind)
async def fsm_bind(message: Message, db, settings, state: FSMContext) -> None:
    if not await require_admin(message, settings):
        return
    try:
        target = resolve_channel_target(message)
    except ValueError as exc:
        await message.answer(str(exc))
        return
    await db.update_group_posting_settings(target_chat_id=target)
    await state.clear()
    warn = positive_id_warning(target)
    await message.answer(
        (warn + "\n" if warn else "") + await channel_status_text(db),
        reply_markup=channel_posting_keyboard(),
    )


@router.message(ChannelPostingFSM.tags)
async def fsm_tags(message: Message, db, settings, state: FSMContext) -> None:
    if not await require_admin(message, settings):
        return
    await db.update_group_posting_settings(tags=message.text or "")
    await state.clear()
    await message.answer(await channel_status_text(db), reply_markup=channel_posting_keyboard())


@router.message(ChannelPostingFSM.interval)
async def fsm_interval(message: Message, db, settings, state: FSMContext) -> None:
    if not await require_admin(message, settings):
        return
    try:
        minutes = int(message.text or "")
    except ValueError:
        await message.answer("Отправь число минут.")
        return
    await db.update_group_posting_settings(interval_minutes=minutes)
    await state.clear()
    await message.answer(await channel_status_text(db), reply_markup=channel_posting_keyboard())
