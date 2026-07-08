import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InputMediaPhoto, Message

from app.keyboards import post_keyboard
from app.models import BooruPost
from app.providers.registry import fallback_search
from app.safety import LimitState, can_search, record_search, validate_tags
from app.ui.sessions import SearchSession, callback_sessions, parse_callback
from app.ui.tags import format_full_tags_messages, format_tag_preview
from app.ui.texts import ALL_PROVIDERS_FAILED, SEARCH_PROMPT, SESSION_EXPIRED

router = Router()
logger = logging.getLogger(__name__)
limit_states: dict[int, LimitState] = {}
post_cache: dict[tuple[int, str], BooruPost] = {}


class SearchInput(StatesGroup):
    waiting_query = State()


async def require_ready(
    message: Message, db, user_id: int | None = None, username: str | None = None
) -> bool:
    user_id = user_id or message.from_user.id
    username = username if username is not None else message.from_user.username
    await db.upsert_user(user_id, username)
    if not await db.is_confirmed(user_id):
        await message.answer("Сначала открой /start и подтверди 18+.")
        return False
    return True


def caption_for(post: BooruPost) -> str:
    tags = format_tag_preview(" ".join(post.tags))
    return (
        f"Источник: {post.provider}\n"
        f"ID: {post.post_id}\n"
        f"Rating: {post.rating or 'unknown'}\n"
        f"Теги: {tags}"
    )[:1024]


async def _delete_message(target: Message, message_id: int) -> None:
    try:
        await target.bot.delete_message(chat_id=target.chat.id, message_id=message_id)
    except Exception as exc:
        logger.warning("failed to delete message %s: %s", message_id, exc)


async def _edit_text_message(target: Message, message_id: int, text: str) -> bool:
    try:
        await target.bot.edit_message_text(chat_id=target.chat.id, message_id=message_id, text=text)
        return True
    except Exception as exc:
        logger.warning("failed to edit text message %s: %s", message_id, exc)
        return False


async def _send_fallback_text(target: Message, key: str, post: BooruPost, page: int) -> Message:
    return await target.answer(
        f"Не удалось отправить изображение. Ссылка: {post.display_url}",
        reply_markup=post_keyboard(key, page),
    )


async def _update_tags_messages(
    target: Message, session: SearchSession, tag_messages: list[str]
) -> None:
    old_ids = list(session.tags_message_ids)
    new_ids: list[int] = []
    for index, text in enumerate(tag_messages):
        if index < len(old_ids):
            message_id = old_ids[index]
            if await _edit_text_message(target, message_id, text):
                new_ids.append(message_id)
                continue
            await _delete_message(target, message_id)
        try:
            sent = await target.answer(text)
            new_ids.append(sent.message_id)
        except Exception as exc:
            logger.warning("failed to send tags message: %s", exc)
    for message_id in old_ids[len(tag_messages) :]:
        await _delete_message(target, message_id)
    session.tags_message_ids = new_ids


async def render_post(
    target: Message,
    key: str,
    post: BooruPost,
    page: int,
    *,
    update_existing: bool = False,
    user_id: int | None = None,
) -> None:
    user_id = user_id or target.from_user.id
    session = callback_sessions.get(key, user_id)
    if not session:
        return
    session.current_post_id = post.post_id
    session.current_page = page
    session.current_provider = post.provider
    session.page = page
    session.provider = post.provider
    tag_messages = format_full_tags_messages(" ".join(post.tags))

    if not update_existing or session.image_message_id is None:
        try:
            sent = await target.answer_photo(
                post.file_url,
                caption=caption_for(post),
                reply_markup=post_keyboard(key, page),
            )
        except Exception as exc:
            logger.warning("failed to send photo: %s", exc)
            try:
                sent = await _send_fallback_text(target, key, post, page)
            except Exception as fallback_exc:
                logger.warning("failed to send fallback post: %s", fallback_exc)
                return
        session.image_message_id = sent.message_id
        session.tags_message_ids = []
        await _update_tags_messages(target, session, tag_messages)
        callback_sessions.update(key, session)
        return

    markup = post_keyboard(key, page)
    try:
        await target.bot.edit_message_media(
            chat_id=target.chat.id,
            message_id=session.image_message_id,
            media=InputMediaPhoto(media=post.file_url, caption=caption_for(post)),
            reply_markup=markup,
        )
    except Exception as exc:
        logger.warning("failed to edit post media: %s", exc)
        await _delete_message(target, session.image_message_id)
        try:
            sent = await target.answer_photo(
                post.file_url, caption=caption_for(post), reply_markup=markup
            )
        except Exception as send_exc:
            logger.warning("failed to send replacement photo: %s", send_exc)
            fallback = f"Не удалось отправить изображение. Ссылка: {post.display_url}"
            if not await _edit_text_message(target, session.image_message_id, fallback):
                try:
                    sent = await target.answer(fallback, reply_markup=markup)
                except Exception as fallback_exc:
                    logger.warning("failed to send replacement fallback: %s", fallback_exc)
                else:
                    session.image_message_id = sent.message_id
            else:
                # Keep the same message id if Telegram allowed editing an existing text fallback.
                pass
        else:
            session.image_message_id = sent.message_id

    await _update_tags_messages(target, session, tag_messages)
    callback_sessions.update(key, session)


async def _edit_existing_failure_message(target: Message, session: SearchSession) -> None:
    if session.image_message_id is None:
        return
    if not await _edit_text_message(target, session.image_message_id, ALL_PROVIDERS_FAILED):
        try:
            await target.bot.edit_message_caption(
                chat_id=target.chat.id,
                message_id=session.image_message_id,
                caption=ALL_PROVIDERS_FAILED,
            )
        except Exception as exc:
            logger.warning("failed to edit failure message: %s", exc)


async def run_search(
    message: Message,
    db,
    settings,
    providers_map,
    query: str,
    page: int = 1,
    *,
    user_id: int | None = None,
    username: str | None = None,
    session_key: str | None = None,
    update_existing: bool = False,
) -> None:
    user_id = user_id or message.from_user.id
    username = username if username is not None else message.from_user.username
    if not await require_ready(message, db, user_id, username):
        return
    ok, blocked = validate_tags(query, user_id=user_id, admin_ids=settings.admin_ids)
    if not ok:
        await message.answer(f"Запрещённые теги: {', '.join(sorted(blocked))}")
        return
    state = limit_states.setdefault(user_id, LimitState())
    allowed, reason = can_search(
        state,
        user_id=user_id,
        admin_ids=settings.admin_ids,
        rate_limit_seconds=settings.rate_limit_seconds,
        daily_limit=settings.daily_limit,
    )
    if not allowed:
        await message.answer(reason)
        return
    provider_name = await db.get_provider(user_id, settings.default_provider)
    mode = await db.get_user_provider_mode(user_id)
    enabled = list(providers_map.items())
    ordered = {}
    if mode == "selected":
        if provider_name in providers_map:
            ordered[provider_name] = providers_map[provider_name]
    elif mode == "rotation" and enabled:
        idx = await db.next_user_provider_cursor(user_id, len(enabled))
        rotated = enabled[idx:] + enabled[:idx]
        ordered = dict(rotated)
    else:  # fallback
        if provider_name in providers_map:
            ordered[provider_name] = providers_map[provider_name]
        for slug, candidate in providers_map.items():
            ordered.setdefault(slug, candidate)
    provider, posts = await fallback_search(ordered, query, settings.result_limit, page)
    record_search(state)
    selected_provider = provider.name if provider else provider_name
    await db.add_history(user_id, selected_provider, query)
    await db.add_tag_usage(user_id, username, selected_provider, query, query.split())
    if not posts:
        if update_existing and session_key:
            session = callback_sessions.get(session_key, user_id)
            if session:
                await _edit_existing_failure_message(message, session)
                return
        await message.answer(ALL_PROVIDERS_FAILED)
        return
    post = posts[0]
    if session_key and update_existing:
        session = callback_sessions.get(session_key, user_id)
        if not session:
            await message.answer(SESSION_EXPIRED)
            return
        session.provider = post.provider
        session.query = query
        session.page = page
        session.current_post_id = post.post_id
        session.current_page = page
        session.current_provider = post.provider
        session.results = posts
        key = session_key
    else:
        session = SearchSession(
            user_id=user_id,
            provider=post.provider,
            query=query,
            page=page,
            current_post_id=post.post_id,
            current_page=page,
            current_provider=post.provider,
            results=posts,
        )
        key = callback_sessions.create(session)
    post_cache[(user_id, post.post_id)] = post
    await render_post(message, key, post, page, update_existing=update_existing, user_id=user_id)


@router.message(Command("search"))
async def search(message: Message, db, settings, providers_map, state: FSMContext) -> None:
    query = message.text.split(maxsplit=1)[1].strip() if len(message.text.split()) > 1 else ""
    if not query:
        await state.set_state(SearchInput.waiting_query)
        await message.answer(SEARCH_PROMPT)
        return
    await run_search(message, db, settings, providers_map, query)


@router.callback_query(lambda c: c.data == "search_input")
async def search_button(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(SearchInput.waiting_query)
    await callback.message.answer(SEARCH_PROMPT)
    await callback.answer()


@router.message(SearchInput.waiting_query, F.text)
async def search_text(message: Message, db, settings, providers_map, state: FSMContext) -> None:
    await state.clear()
    await run_search(message, db, settings, providers_map, message.text.strip())


@router.message(Command("random"))
async def random_post(message: Message, db, settings, providers_map) -> None:
    await run_search(message, db, settings, providers_map, "rating:explicit")


@router.callback_query(lambda c: c.data == "random")
async def random_button(callback: CallbackQuery, db, settings, providers_map) -> None:
    await run_search(
        callback.message,
        db,
        settings,
        providers_map,
        "rating:explicit",
        user_id=callback.from_user.id,
        username=callback.from_user.username,
    )
    await callback.answer()


@router.callback_query(lambda c: c.data and c.data.startswith(("next:", "prev:", "repeat:")))
async def page_or_repeat(callback: CallbackQuery, db, settings, providers_map) -> None:
    parsed = parse_callback(callback.data)
    if not parsed:
        await callback.answer("Кнопка устарела. Открой меню заново.", show_alert=True)
        return
    action, key = parsed
    session = callback_sessions.get(key, callback.from_user.id)
    if not session:
        await callback.answer(SESSION_EXPIRED, show_alert=True)
        return
    page = session.page
    if action == "next":
        page += 1
    elif action == "prev":
        page = max(1, page - 1)
    elif action == "repeat":
        page = session.page
    await db.set_provider(callback.from_user.id, session.provider)
    await run_search(
        callback.message,
        db,
        settings,
        providers_map,
        session.query,
        page,
        user_id=callback.from_user.id,
        username=callback.from_user.username,
        session_key=key,
        update_existing=True,
    )
    await callback.answer()
